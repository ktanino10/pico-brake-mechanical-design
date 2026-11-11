"""Package only verified enclosure outputs and the public inputs required to reproduce them."""
from pathlib import Path
import hashlib
import json
import zipfile

from enclosure_policy import validate_enclosure_ids
from public_files import ENCLOSURE_ZIP_FILES
from public_scan import inspect_file

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_generated():
    manifest_path = ROOT/"data/enclosure-checksums.json"
    manifest = json.loads(manifest_path.read_text())
    report = json.loads((ROOT/"validation/enclosure-cad.json").read_text())
    assembly = json.loads((ROOT/"data/enclosure-assembly.json").read_text())
    validate_enclosure_ids(part["id"] for part in assembly["parts"])
    if report["status"] != "PASS" or report["model_parts"] != 526 or report["fasteners"] != 200:
        raise ValueError("A complete nominal geometry/readback receipt is required")
    for item in report["readback"]["files"]:
        if digest(ROOT/item["path"]) != item["sha256"]:
            raise ValueError("CAD changed after readback")
    for name,value in report["input_sha256"].items():
        if digest(ROOT/name) != value:
            raise ValueError("Enclosure input changed after geometry verification: "+name)
    for name,value in report["generator_sha256"].items():
        if digest(ROOT/"scripts"/name) != value:
            raise ValueError("Enclosure generator changed after geometry verification: "+name)
    for entry in manifest["files"]:
        if entry["path"].endswith(".zip"):
            continue
        if digest(ROOT/entry["path"]) != entry["sha256"]:
            raise ValueError("Generated enclosure payload changed after verification")
    return manifest


def audit_enclosure():
    manifest = validate_generated()
    browser = json.loads((ROOT/"validation/enclosure-browser.json").read_text())
    if (manifest.get("downloads_ready") is not True or browser.get("status") != "PASS" or
            len(browser.get("downloads",[])) != 3):
        raise ValueError("Enclosure browser/download verification is incomplete")
    for row in [*browser["inputs"],*browser["downloads"]]:
        if digest(ROOT/row["path"]) != row["sha256"]:
            raise ValueError("Enclosure changed after browser verification: "+row["path"])
    target = ROOT/"downloads/enclosure-nominal.zip"
    entry = next(row for row in manifest["files"] if row["path"] == "downloads/enclosure-nominal.zip")
    if digest(target) != entry["sha256"]:
        raise ValueError("Curated enclosure ZIP changed after verification")
    with zipfile.ZipFile(target) as archive:
        if set(archive.namelist()) != set(ENCLOSURE_ZIP_FILES) or archive.testzip() is not None:
            raise ValueError("Curated enclosure archive failed its manifest/CRC check")
        for name in ENCLOSURE_ZIP_FILES:
            if hashlib.sha256(archive.read(name)).hexdigest() != digest(ROOT/name):
                raise ValueError("Enclosure ZIP member changed: "+name)
    return {"status":"PASS","model_parts":526,"fasteners":200,"zip_members":len(ENCLOSURE_ZIP_FILES),
            "zip_sha256":digest(target),"actual_hardware_compatibility":"unverified/blocked"}


def main():
    manifest_path = ROOT/"data/enclosure-checksums.json"
    manifest = validate_generated()
    target = ROOT/"downloads/enclosure-nominal.zip"
    with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name in ENCLOSURE_ZIP_FILES:
            path = ROOT/name
            inspect_file(path,name)
            info = zipfile.ZipInfo(name,(2020,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info,path.read_bytes())
    inspect_file(target,target.name)
    with zipfile.ZipFile(target) as archive:
        if set(archive.namelist()) != set(ENCLOSURE_ZIP_FILES) or archive.testzip() is not None:
            raise ValueError("Curated enclosure archive failed its manifest/CRC check")
        for name in ENCLOSURE_ZIP_FILES:
            if hashlib.sha256(archive.read(name)).hexdigest() != digest(ROOT/name):
                raise ValueError("ZIP member differs from the verified working bytes")
    entries = [item for item in manifest["files"] if item["path"] != "downloads/enclosure-nominal.zip"]
    entries.append({"path":"downloads/enclosure-nominal.zip","sha256":digest(target),"bytes":target.stat().st_size})
    manifest["files"] = entries
    manifest["zip_members"] = list(ENCLOSURE_ZIP_FILES)
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"zip_members":len(ENCLOSURE_ZIP_FILES),"sha256":digest(target),"bytes":target.stat().st_size}))


if __name__ == "__main__":
    main()
