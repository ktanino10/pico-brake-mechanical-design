from collections import Counter
import copy
import csv
import io
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_c08_procurement as procurement
from public_policy import ALLOWED, REFERENCES
from public_scan import inspect_bytes


class ProcurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.electrical = json.loads((ROOT / "data/c08-procurement-electrical.json").read_text())
        cls.data = procurement.build(cls.electrical)
        cls.rows = {p["id"]: p for p in cls.data["items"]}

    def test_every_source_id_has_one_procurement_owner(self):
        seen = Counter(pid for row in self.data["items"] for pid in row["c08_ids"])
        self.assertEqual(set(seen), set(ALLOWED) | set(REFERENCES))
        self.assertEqual(set(seen.values()), {1})
        with (ROOT / "data/parts.csv").open() as source:
            csv_source = list(csv.DictReader(source))
        self.assertEqual(len(csv_source), len(seen))
        bearing = self.rows["C08-BEARING_ASSEMBLY"]
        self.assertEqual(len(bearing["c08_ids"]), 12)
        self.assertEqual(bearing["one_axis_quantity"], 1)
        self.assertEqual(bearing["three_axis_reference_quantity"], 3)
        for pid in REFERENCES:
            row = self.rows[self.data["coverage"][pid]]
            self.assertEqual(row["category"], "対象外")
            self.assertEqual(row["one_axis_quantity"], 0)

    def test_mixed_threads_and_non_threaded_pins_remain_distinct(self):
        self.assertIn("M2.5×8", self.rows["C08-RETAINER_BOLT"]["current_spec"])
        self.assertIn("M2×6", self.rows["C08-SPRING_ROOT_BOLT"]["current_spec"])
        self.assertIn("M4×8", self.rows["C08-RIM_BOLT"]["current_spec"])
        self.assertNotIn("M2×4", self.rows["C08-HUB_CONNECT_PIN"]["current_spec"])
        self.assertEqual(self.rows["C08-MOTOR_INTERFACE_BOLT"]["cad_shape_count"], 3)
        self.assertEqual(self.rows["C08-MOTOR_INTERFACE_BOLT"]["one_axis_quantity"], 0)
        self.assertTrue(all(r["after_M3_redesign_quantity"] is None for r in self.rows.values()))
        self.assertTrue(all(r["physical_qualified"] is False for r in self.rows.values()))

    def test_shared_unknown_owned_and_pack_quantities_do_not_get_tripled(self):
        for key in ("EP06", "EP07", "EP17", "EP18", "EP19", "TOOL-CALIPER", "TEST-FIXTURE"):
            self.assertEqual(self.rows[key]["three_axis_reference_quantity"], 1, key)
            self.assertEqual(self.rows[key]["additional_for_three_axes"], 0, key)
        for key in ("EP09", "EP14", "EP15", "FUSES", "POWER-WIRE"):
            self.assertIsNone(self.rows[key]["one_axis_quantity"], key)
            self.assertIsNone(self.rows[key]["three_axis_reference_quantity"], key)
        for key in ("OWN-MOTOR", "OWN-HARNESS"):
            self.assertEqual(self.rows[key]["owned_quantity"], 1)
            self.assertEqual(self.rows[key]["new_purchase_for_one_axis"], 0)
            self.assertEqual(self.rows[key]["additional_for_three_axes"], 2)
        self.assertIn("20本/袋", self.rows["C08-STATOR_BOLT"]["purchase_unit"])
        self.assertEqual(self.rows["C08-STATOR_BOLT"]["one_axis_quantity"], 4)
        self.assertIn("ケーブル1本", self.rows["EP07"]["included_and_duplicates"])
        self.assertIn("センサー1個", self.rows["EP18"]["included_and_duplicates"])
        self.assertIsNone(self.rows["EP14"]["display_price_jpy"])

    def test_missing_or_duplicate_electrical_evidence_is_rejected(self):
        missing = copy.deepcopy(self.electrical)
        missing["items"].pop()
        duplicate = copy.deepcopy(self.electrical)
        duplicate["items"][-1] = duplicate["items"][0]
        for evidence in (missing, duplicate):
            with self.assertRaisesRegex(ValueError, "19 distinct"):
                procurement.build(evidence)
        with patch.dict(procurement.CONFIG, {"YOKE": procurement.CONFIG["YOKE"][:1] + ("unknown-source",) + procurement.CONFIG["YOKE"][2:]}):
            with self.assertRaisesRegex(ValueError, "Unknown supplier"):
                procurement.build(self.electrical)

    def test_csv_is_reproducible_complete_and_preserves_unknown_cells(self):
        text = procurement.csv_text(self.data)
        self.assertEqual((ROOT / "data/c08-procurement.csv").read_text(), text)
        saved = json.loads((ROOT / "data/c08-procurement-coverage.json").read_text())
        self.assertEqual(saved, self.data)
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(rows), len(self.rows))
        self.assertTrue(all(None not in r and len(r) == len(procurement.FIELDS) for r in rows))
        by_id = {r["調達ID"]: r for r in rows}
        self.assertEqual(by_id["FUSES"]["現行1軸必要数"], "")
        self.assertEqual(by_id["EP14"]["確認価格JPY"], "")
        self.assertEqual(by_id["OWN-HARNESS"]["1軸新規購入数"], "0")
        guide = (ROOT / "docs/C08_PROCUREMENT.md").read_text()
        self.assertIn(f"必要品を{len(rows)}行", guide)

    def test_concrete_sources_and_local_document_links(self):
        for source in self.data["sources"].values():
            parsed = urlsplit(source["url"])
            self.assertEqual(parsed.scheme, "https")
            self.assertIsNone(parsed.username)
            self.assertIsNone(parsed.password)
            self.assertTrue(parsed.path.strip("/"), source["url"])
            for field in ("checked_on", "kind", "confirmed", "limits"):
                self.assertTrue(source[field])
        guide = ROOT / "docs/C08_PROCUREMENT.md"
        for link in re.findall(r"\]\(([^)]+)\)", guide.read_text()):
            if not urlsplit(link).scheme:
                self.assertTrue((guide.parent / link.split("#")[0]).resolve().is_file(), link)
        for page in ("motion.html", "index.html"):
            self.assertIn('href="./docs/C08_PROCUREMENT.md"', (ROOT / page).read_text())
        for name in ("docs/C08_PROCUREMENT.md", "data/c08-procurement.csv",
                     "data/c08-procurement-coverage.json", "data/c08-procurement-electrical.json",
                     "scripts/build_c08_procurement.py"):
            inspect_bytes(name, (ROOT / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
