"""Fail-closed inspection of public bytes, nested CAD/ZIP and PNG metadata."""
from pathlib import Path, PurePosixPath
import binascii
import hashlib
import io
import re
import stat
import struct
import zipfile
import zlib
import xml.etree.ElementTree as ET

from public_policy import ALLOWED, REFERENCES, SOURCE_SHA256

MAX_MEMBER = 64 * 1024 * 1024
MAX_ARCHIVE = 128 * 1024 * 1024
ZERO_UUID = b"00000000-0000-0000-0000-000000000000"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PATTERNS = (
    ("personal-local-path", re.compile(rb"(?i)(?:/(?:Users|home)/[^\s/'\"]+|[A-Z]:\\Users\\)")),
    ("session-storage-path", re.compile(rb"(?i)\.copilot[/\\]session-state")),
    ("unnecessary-uuid", re.compile(rb"(?i)[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")),
    ("github-token", re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("private-key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(rb"AKIA[A-Z0-9]{16}")),
    ("credential-in-url", re.compile(rb"https?://[A-Za-z0-9._%-]+:[^/\s@]+@")),
)


class PublicScanError(ValueError):
    pass


def scan_text(data, name):
    for reason, pattern in PATTERNS:
        if pattern.search(data):
            raise PublicScanError(f"{name}: {reason}")


def inflate(data):
    decoder = zlib.decompressobj()
    result = decoder.decompress(data, MAX_MEMBER + 1)
    if len(result) > MAX_MEMBER or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data:
        raise PublicScanError("Malformed or oversized compressed metadata")
    return result


def inspect_png(data, name):
    if not data.startswith(PNG_SIGNATURE):
        raise PublicScanError(f"{name}: invalid PNG signature")
    offset, text_chunks, ended, chunks = 8, [], False, []
    while offset < len(data):
        if offset + 12 > len(data):
            raise PublicScanError(f"{name}: truncated PNG chunk")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + length + 12
        if length > MAX_MEMBER or end > len(data):
            raise PublicScanError(f"{name}: PNG chunk bounds")
        payload = data[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", data[offset + 8 + length:end])[0]
        if (binascii.crc32(kind + payload) & 0xFFFFFFFF) != crc:
            raise PublicScanError(f"{name}: PNG CRC mismatch")
        chunks.append(kind)
        if kind == b"tEXt":
            if b"\0" not in payload:
                raise PublicScanError(f"{name}: malformed tEXt")
            text_chunks.append((kind, payload.replace(b"\0", b" ")))
        elif kind == b"zTXt":
            key, separator, rest = payload.partition(b"\0")
            if not separator or len(rest) < 2 or rest[0] != 0:
                raise PublicScanError(f"{name}: malformed zTXt")
            text_chunks.append((kind, key + b" " + inflate(rest[1:])))
        elif kind == b"iTXt":
            key, separator, rest = payload.partition(b"\0")
            if not separator or len(rest) < 4 or rest[0] not in (0, 1) or rest[1] != 0:
                raise PublicScanError(f"{name}: malformed iTXt")
            language, separator, rest2 = rest[2:].partition(b"\0")
            translated, separator2, content = rest2.partition(b"\0")
            if not separator or not separator2:
                raise PublicScanError(f"{name}: malformed iTXt fields")
            text_chunks.append((kind, key + b" " + language + b" " + translated + b" " +
                                (inflate(content) if rest[0] else content)))
        elif kind == b"IEND":
            if length != 0 or end != len(data):
                raise PublicScanError(f"{name}: invalid PNG end")
            ended = True
        offset = end
    if not ended or not chunks or chunks[0] != b"IHDR" or b"IDAT" not in chunks:
        raise PublicScanError(f"{name}: incomplete PNG")
    for _, text in text_chunks:
        scan_text(text, name)
    if text_chunks:
        raise PublicScanError(f"{name}: unnecessary PNG textual metadata")
    return {"png_crc_checked": True, "png_text_chunks": 0}


def inspect_native(members, name):
    if "Document.xml" not in members:
        raise PublicScanError(f"{name}: native Document.xml missing")
    tree = ET.fromstring(members["Document.xml"])
    definitions = tree.find("Objects")
    if definitions is None:
        raise PublicScanError(f"{name}: native object table missing")
    features = set()
    if any(obj.tag not in {"Object", "ObjectDeps"} for obj in definitions):
        raise PublicScanError(f"{name}: unsupported native object-table entry")
    for obj in definitions.findall("Object"):
        kind = obj.get("type")
        if kind == "Part::Feature":
            features.add(obj.get("name"))
        elif kind != "App::DocumentObjectGroup":
            raise PublicScanError(f"{name}: unsupported native object type")
    public = set(ALLOWED) | set(REFERENCES)
    single = {"Z_" + part for part in public}
    three = {axis + "_" + part for axis in "XYZ" for part in public}
    if features not in (single, three):
        raise PublicScanError(f"{name}: forbidden or incomplete native geometry")
    for obj in tree.findall(".//ObjectData/Object"):
        for prop in obj.findall("./Properties/Property"):
            kind = prop.get("type", "")
            if "PropertyXLink" in kind or ("PropertyLink" in kind and prop.get("name") != "Group"):
                raise PublicScanError(f"{name}: native external/dependent link")
            if prop.get("name") == "SourceLeaf":
                raise PublicScanError(f"{name}: original source leaf metadata")
    allowed_members = {"Document.xml", "GuiDocument.xml", "StringHasher.Table.txt"}
    allowed_members.update(part + suffix for part in features for suffix in (".Shape.brp", ".Shape.Map.txt"))
    for member in members:
        if member not in allowed_members:
            raise PublicScanError(f"{name}: unapproved native member")
    if any(part + ".Shape.brp" not in members for part in features):
        raise PublicScanError(f"{name}: native shape payload missing")
    return {"native_shapes": len(features), "native_external_links": 0}


def inspect_bytes(name, data, depth=0):
    if hashlib.sha256(data).hexdigest() == SOURCE_SHA256:
        raise PublicScanError(f"{name}: full protected C08 native is forbidden")
    if len(data) > MAX_MEMBER or depth > 3:
        raise PublicScanError(f"{name}: payload limits exceeded")
    if data.startswith(PNG_SIGNATURE) or name.lower().endswith(".png"):
        return inspect_png(data, name)
    if data.startswith(b"PK\x03\x04"):
        members, total = {}, 0
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.infolist():
                member_path = PurePosixPath(entry.filename)
                total += entry.file_size
                if (entry.file_size > MAX_MEMBER or total > MAX_ARCHIVE or entry.is_dir() or
                        member_path.is_absolute() or ".." in member_path.parts or
                        any(part.startswith(".") for part in member_path.parts) or
                        "\\" in entry.filename or entry.filename in members or
                        stat.S_ISLNK(entry.external_attr >> 16)):
                    raise PublicScanError(f"{name}: unsafe archive member")
                payload = archive.read(entry)
                members[entry.filename] = payload
                inspect_bytes(entry.filename, payload, depth + 1)
        if name.lower().endswith(".fcstd"):
            return inspect_native(members, name)
        return {"zip_members": len(members), "uncompressed_bytes": total}
    scan_text(data, name)
    if name.lower().endswith((".step", ".stp")):
        text = data.decode("ascii")
        header = text.split("ENDSEC;", 1)[0]
        if "FILE_NAME('public-brake.step'" not in header:
            raise PublicScanError(f"{name}: unexpected STEP identity header")
        if not re.search(r"\.MILLI\.,\.METRE\.", text):
            raise PublicScanError(f"{name}: STEP mm units missing")
    return {"bytes_scanned": len(data)}


def inspect_file(path, public_name=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise PublicScanError("Only ordinary files are public payloads")
    return inspect_bytes(public_name or path.name, path.read_bytes())
