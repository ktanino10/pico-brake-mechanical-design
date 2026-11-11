"""Pure-Python checks of the local full-candidate roster, provenance and persisted CAD evidence."""
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from enclosure_policy import (CAGE_IDS, ENCLOSURE_IDS, HOLDER_IDS, PUBLIC_BRAKE_SHA256,
                              PUBLIC_CATALOG_SHA256, validate_enclosure_ids, validate_public_brake_identity)
from public_policy import SOURCE_SHA256
from public_scan import inspect_file


class EnclosureTests(unittest.TestCase):
    def test_exact_roster(self):
        self.assertEqual((len(CAGE_IDS),len(HOLDER_IDS),len(ENCLOSURE_IDS)),(54,28,526))
        validate_enclosure_ids(ENCLOSURE_IDS)
        with self.assertRaises(ValueError):
            validate_enclosure_ids([*ENCLOSURE_IDS,"SRC_ORIGINAL"])
        with self.assertRaises(ValueError):
            validate_enclosure_ids(ENCLOSURE_IDS[1:])

    def test_original_input_identity_rejected(self):
        with self.assertRaises(ValueError):
            validate_public_brake_identity(SOURCE_SHA256,PUBLIC_CATALOG_SHA256)
        self.assertEqual(hashlib.sha256((ROOT/"downloads/brake-single.FCStd").read_bytes()).hexdigest(),PUBLIC_BRAKE_SHA256)
        self.assertEqual(hashlib.sha256((ROOT/"data/assembly.json").read_bytes()).hexdigest(),PUBLIC_CATALOG_SHA256)

    def test_all_reference_leaves_accounted_for(self):
        coverage = json.loads((ROOT/"data/enclosure-source-coverage.json").read_text())
        self.assertEqual(len(coverage["rows"]),83)
        self.assertEqual(len({row["source_leaf"] for row in coverage["rows"]}),83)
        motor = [row for row in coverage["rows"] if "external_assembly_group" in row]
        self.assertEqual(len(motor),12)
        self.assertEqual(len({row["external_assembly_group"] for row in motor}),3)
        for row in coverage["rows"]:
            self.assertFalse(row["original_geometry_redistributed"])
            self.assertFalse(row["original_interchangeability_claimed"])
            self.assertTrue(set(row["target_parts"]).issubset(ENCLOSURE_IDS))

    def test_persisted_brep_evidence_and_file_identity(self):
        report = json.loads((ROOT/"validation/enclosure-cad.json").read_text())
        self.assertEqual(report["status"],"PASS")
        self.assertEqual(report["readback"]["solids"],526)
        self.assertEqual(len(report["geometry"]["declared_thread_presence"]),200)
        self.assertEqual(len(report["geometry"]["bounded_threads"]),200)
        self.assertEqual(len(report["fastener_lengths"]),200)
        self.assertEqual(report["geometry"]["undeclared_positive_intersections"],0)
        self.assertGreater(report["cap_scope_extension"]["separation_mm"],12)
        for row in report["readback"]["files"]:
            self.assertEqual(hashlib.sha256((ROOT/row["path"]).read_bytes()).hexdigest(),row["sha256"])
        for name,value in report["generator_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT/"scripts"/name).read_bytes()).hexdigest(),value,name)
        mutation = report["holder_condition_controls"]
        self.assertAlmostEqual(mutation["changed_board_thickness_mm"],2)
        self.assertEqual(mutation["changed_joint_grip_mm"],5.5)
        self.assertEqual(mutation["changed_joint_engagement_mm"],4.5)
        self.assertTrue(mutation["stale_total_length_rejected"])

    def test_fresh_native_and_step_privacy(self):
        result = inspect_file(ROOT/"downloads/enclosure-nominal.FCStd")
        self.assertEqual(result["native_shapes"],526)
        inspect_file(ROOT/"downloads/enclosure-nominal.step")


if __name__ == "__main__":
    unittest.main()
