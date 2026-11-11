from pathlib import Path
import binascii
import io
import json
import struct
import sys
import unittest
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from public_policy import ALLOWED, REFERENCES, make_policy, validate_request
from public_scan import PNG_SIGNATURE, PublicScanError, inspect_bytes, inspect_png
from geometry_contract import axis_bounds, axis_point, expected_instances, mesh_moments, require_pose


def chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)


def png(metadata=b""):
    return (PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            metadata + chunk(b"IDAT", zlib.compress(b"\0\x10\x20\x30")) + chunk(b"IEND", b""))


class PublicPolicyTests(unittest.TestCase):
    def test_exact_composition(self):
        self.assertEqual(len(ALLOWED), 145)
        self.assertEqual(len(REFERENCES), 4)
        validate_request(ALLOWED)

    def test_original_and_modified_shape_names_rejected(self):
        for name in ("WHEEL", "LOAD_FRAME", "SRC_Part__Feature12", "CORNER_BOLT_0",
                     "NOMINAL_MOTOR_SHAFT", "YOKE_99", "Z_YOKE"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_request([name])

    def test_duplicate_requested_shape_rejected(self):
        with self.assertRaises(ValueError):
            validate_request(["YOKE", "YOKE"])

    def test_unreviewed_shape_never_included(self):
        policy = make_policy(["Z_" + name for name in ALLOWED] + ["Z_WHEEL", "Z_LOAD_FRAME", "SRC_Part__Feature12"])
        self.assertEqual(len(policy["included"]), 149)
        self.assertEqual(len(policy["excluded"]), 3)
        for row in policy["included"]:
            self.assertFalse(row["external_links_copied"])
        for row in policy["included"][-4:]:
            self.assertEqual(row["method"], "generate-independent-reference-primitive")

    def test_missing_audited_part_rejected(self):
        with self.assertRaises(ValueError):
            make_policy(["Z_" + name for name in ALLOWED[1:]])


class MetadataTests(unittest.TestCase):
    def test_plain_png_crc(self):
        self.assertTrue(inspect_png(png(), "image.png")["png_crc_checked"])

    def test_png_bad_crc_rejected(self):
        image = bytearray(png())
        image[-1] ^= 1
        with self.assertRaisesRegex(PublicScanError, "CRC"):
            inspect_png(bytes(image), "image.png")

    def test_text_metadata_rejected_in_all_encodings(self):
        private_path = ("/" + "Users" + "/example/private/model.blend").encode()
        samples = {
            "tEXt": b"File\0" + private_path,
            "zTXt": b"File\0\0" + zlib.compress(private_path),
            "iTXt-uncompressed": b"File\0\0\0ja\0File\0" + private_path,
            "iTXt-compressed": b"File\0\1\0ja\0File\0" + zlib.compress(private_path),
        }
        for name, payload in samples.items():
            with self.subTest(name=name), self.assertRaisesRegex(PublicScanError, "personal-local-path"):
                inspect_png(png(chunk(name[:4].encode(), payload)), "image.png")

    def test_benign_text_metadata_also_removed_from_public_scope(self):
        with self.assertRaisesRegex(PublicScanError, "unnecessary"):
            inspect_png(png(chunk(b"tEXt", b"Software\0Renderer")), "image.png")

    def test_compressed_text_is_actually_parsed(self):
        with self.assertRaises((PublicScanError, zlib.error)):
            inspect_png(png(chunk(b"zTXt", b"File\0\0not-zlib")), "image.png")

    def test_incomplete_png_rejected(self):
        with self.assertRaises(PublicScanError):
            inspect_png(png()[:-12], "image.png")

    def test_private_path_in_step_header_rejected(self):
        data = ("FILE_NAME('/" + "Users" + "/example/model.step');").encode()
        with self.assertRaisesRegex(PublicScanError, "personal-local-path"):
            inspect_bytes("model.step", data)

    def test_nested_archive_inspected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Document.xml", ("<path>/" + "Users" + "/example/file</path>").encode())
        with self.assertRaisesRegex(PublicScanError, "personal-local-path"):
            inspect_bytes("bundle.zip", buffer.getvalue())

    def test_archive_traversal_rejected(self):
        for name in ("../file", "/absolute", ".git/config"):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr(name, "not public")
            with self.subTest(name=name), self.assertRaisesRegex(PublicScanError, "unsafe"):
                inspect_bytes("bundle.zip", buffer.getvalue())

    def test_github_token_rejected(self):
        with self.assertRaisesRegex(PublicScanError, "github-token"):
            inspect_bytes("note.txt", ("ghp_" + "X" * 36).encode())

    def test_only_the_public_part_set_is_allowed_in_native(self):
        buffer = io.BytesIO()
        xml = '<Document><Objects><Object type="Part::Feature" name="SRC_Part__Feature12"/></Objects></Document>'
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Document.xml", xml)
        with self.assertRaisesRegex(PublicScanError, "forbidden"):
            inspect_bytes("renamed.FCStd", buffer.getvalue())


class GeometryContractTests(unittest.TestCase):
    def test_independent_axis_conventions(self):
        self.assertEqual(axis_point([1, 2, 3], "Z"), [1, 2, 3])
        self.assertEqual(axis_point([1, 2, 3], "X"), [3, -2, 1])
        self.assertEqual(axis_point([1, 2, 3], "Y"), [1, 3, -2])
        self.assertEqual(axis_bounds([-1, 2, -4, 3, 5, 6], "X"), [-4, -5, -1, 6, -2, 3])

    def test_translated_tetrahedron_centroid(self):
        vertices = [[10, 20, 30], [11, 20, 30], [10, 21, 30], [10, 20, 31]]
        volume, centroid = mesh_moments(vertices, [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
        self.assertAlmostEqual(volume, 1 / 6)
        for actual, expected in zip(centroid, [10.25, 20.25, 30.25]):
            self.assertAlmostEqual(actual, expected)

    def test_bad_pose_is_rejected_against_independent_catalog(self):
        part = {"id": "SPRING_1", "bbox_mm": [1, 2, 3, 4, 5, 6],
                "center_of_mass_mm": [2, 3, 4], "volume_mm3": 10,
                "solid_count": 1, "is_reference": False}
        expected = expected_instances([part], ("Z",))["Z_SPRING_1"]
        require_pose(part["bbox_mm"], part["center_of_mass_mm"], expected, "fixture")
        with self.assertRaisesRegex(ValueError, "Independent world pose mismatch"):
            require_pose([2, 2, 3, 5, 5, 6], [3, 3, 4], expected, "fixture")


if __name__ == "__main__":
    unittest.main()
