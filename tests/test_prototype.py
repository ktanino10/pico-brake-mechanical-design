"""Contracts for the R1 files, independently of the CAD application's saved objects."""
import collections
import csv
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "prototype/mechanical"
sys.path.insert(0, str(ROOT / "scripts"))
from geometry_contract import mesh_moments
from public_files import WEB_FILES, ZIP_FILES, ENCLOSURE_ZIP_FILES


class PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DATA / "manifest.json").read_text())
        with (ROOT / "data/prototype-bom.csv").open(newline="") as stream:
            reader = csv.DictReader(stream)
            cls.rows = list(reader)
            cls.fields = reader.fieldnames

    def test_selected_inventory_and_price_scopes(self):
        self.assertEqual(len(self.fields), 19)
        self.assertEqual(len({row["id"] for row in self.rows}), len(self.rows))
        sources = set(re.findall(r"^## (S\d{2}):", (ROOT / "docs/PROTOTYPE_EVIDENCE.md").read_text(), re.M))
        gates = set(re.findall(r"^\| ([EM]\d{2}) \|", (ROOT / "docs/PROTOTYPE_WORKSHEET.md").read_text(), re.M))
        for row in self.rows:
            with self.subTest(row=row["id"]):
                self.assertNotIn(None, row)
                self.assertNotIn(None, row.values())
                self.assertLessEqual(set(row["資料ID"].split(";")), sources)
                self.assertLessEqual(set(row["選定条件"].split(";")), gates)
                for key in ("必要数", "新規購入数", "参考単価_税込円"):
                    if row[key]:
                        self.assertGreaterEqual(Decimal(row[key]), 0)
                for value in row.values():
                    self.assertFalse(value.lstrip().startswith(("=", "+", "-", "@")))
                if row["調達区分"] in ("所有済み", "同梱", "PLA印刷", "採用なし"):
                    self.assertEqual(row["新規購入数"], "0")
        totals = {}
        for scope in ("参考小計対象", "機械追加参考"):
            totals[scope] = sum(Decimal(r["参考単価_税込円"]) * Decimal(r["新規購入数"])
                                for r in self.rows if r["価格扱い"] == scope)
        self.assertEqual(totals["参考小計対象"], Decimal("20565"))
        self.assertEqual(totals["機械追加参考"], Decimal("13291.3"))
        lookup = {r["id"]: r for r in self.rows}
        self.assertEqual(lookup["M03"]["新規購入数"], "0")
        self.assertEqual(lookup["M21"]["新規購入数"], "1")
        self.assertEqual(lookup["E03"]["候補型番"], "ADA-4409 / Switch Science6007")
        self.assertIn("MAKER-REFLECT", lookup["S01"]["候補型番"])

    def test_rotor_cutting_geometry_matches_independent_inertia(self):
        tokens = (DATA / "rotor-cut.dxf").read_text().splitlines()
        self.assertIn("$INSUNITS", tokens)
        self.assertEqual(tokens[tokens.index("$INSUNITS") + 2], "4")
        circles = []
        for i, token in enumerate(tokens):
            if token != "CIRCLE":
                continue
            fields = {}
            for j in range(i + 1, len(tokens) - 1, 2):
                if tokens[j] == "0":
                    break
                fields[tokens[j]] = tokens[j + 1]
            circles.append(tuple(float(fields[k]) for k in ("10", "20", "40")))
        self.assertEqual(len(circles), 8)
        self.assertEqual(circles[0], (0, 0, 30))
        self.assertEqual(circles[1], (0, 0, 6.05))
        for x, y, radius in circles[2:]:
            self.assertAlmostEqual(math.hypot(x, y), 9.5)
            self.assertEqual(radius, 1.6)
        rho, t, ro, ri, hole, pcd = 7930, .001, .03, .00605, .0016, .0095
        mass = rho * t * math.pi * (ro**2 - ri**2 - 6 * hole**2)
        inertia = rho * t * math.pi / 2 * (ro**4 - ri**4)
        inertia -= 6 * rho * t * math.pi * hole**2 * (pcd**2 + hole**2 / 2)
        self.assertAlmostEqual(self.manifest["physics"]["rotor_mass_kg"], mass, places=10)
        self.assertAlmostEqual(self.manifest["physics"]["rotor_inertia_kg_m2"], inertia, places=12)
        self.assertIsNone(self.manifest["physics"]["motor_rotor_inertia_kg_m2"])

    def test_printable_meshes_are_closed_and_match_presave_volume(self):
        printable = [p for p in self.manifest["parts"] if "stl" in p]
        self.assertEqual(len(printable), sum(int(r["必要数"]) for r in self.rows if r["調達区分"] == "PLA印刷"))
        for part in printable:
            with self.subTest(part=part["id"]):
                data = (DATA / part["stl"]).read_bytes()
                count = struct.unpack("<I", data[80:84])[0]
                self.assertEqual(len(data), 84 + count * 50)
                vertices, faces, edges = [], [], collections.Counter()
                for i in range(count):
                    triangle = struct.unpack("<12fH", data[84 + i * 50:134 + i * 50])
                    points = [tuple(triangle[j:j + 3]) for j in (3, 6, 9)]
                    start = len(vertices)
                    vertices.extend(points)
                    faces.append((start, start + 1, start + 2))
                    for a, b in ((0, 1), (1, 2), (2, 0)):
                        edges[tuple(sorted((points[a], points[b])))] += 1
                self.assertTrue(all(n == 2 for n in edges.values()))
                volume, _ = mesh_moments(vertices, faces)
                self.assertLess(abs(volume - part["volume_mm3"]) / part["volume_mm3"], .01)
                self.assertAlmostEqual(min(v[2] for v in vertices), 0, places=5)

    def test_fastener_stacks_and_motion_window_are_consistent(self):
        with (DATA / "joints.csv").open(newline="") as stream:
            joints = list(csv.DictReader(stream))
        totals = collections.Counter()
        for joint in joints:
            totals[joint["screw"]] += int(joint["quantity"])
        self.assertEqual(dict(totals), self.manifest["fastener_totals"])
        self.assertEqual(sum(totals.values()), 75)
        self.assertEqual(next(r["必要数"] for r in self.rows if r["id"] == "F01"), "75")
        rotor_joint = next(j for j in joints if j["joint"] == "Rotor to hub")
        self.assertEqual(Decimal(rotor_joint["grip_mm"]) + Decimal(rotor_joint["thread_engagement_mm"]), 6)
        strokes = [s["stroke_mm"] for s in self.manifest["checks"]["kinematic_samples"]]
        self.assertTrue(all(.3 <= s <= 1.5 for s in strokes))
        self.assertTrue(all(a > b for a, b in zip(strokes, strokes[1:])))
        self.assertGreaterEqual(self.manifest["checks"]["minimum_sensor_jam_nut_space_mm"], 4.1)
        self.assertGreaterEqual(self.manifest["checks"]["rotor_guard_clearance_min_mm"], 20)
        self.assertFalse(self.manifest["physical_ready"])

    def test_svg_links_and_curated_archive(self):
        for path in DATA.glob("*.svg"):
            ET.fromstring(path.read_bytes())
        for path in [ROOT / "PROTOTYPE.md", *sorted((ROOT / "docs").glob("PROTOTYPE*.md"))]:
            for target in re.findall(r"\[[^\]]+\]\(([^\s)]+)\)", path.read_text()):
                if target.startswith(("http://", "https://", "#")):
                    continue
                file = (path.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(file.is_relative_to(ROOT), (path, target))
                self.assertTrue(file.is_file(), (path, target))
        expected = {r["path"] for r in self.manifest["files"]} | {"manifest.json"}
        with zipfile.ZipFile(DATA / "prototype-mechanical.zip") as archive:
            self.assertEqual(set(archive.namelist()), expected)
            self.assertIsNone(archive.testzip())
            for name in expected:
                self.assertEqual(archive.read(name), (DATA / name).read_bytes())
        for row in self.manifest["files"]:
            self.assertEqual(hashlib.sha256((DATA / row["path"]).read_bytes()).hexdigest(), row["sha256"])
            public = "prototype/mechanical/" + row["path"]
            self.assertIn(public, WEB_FILES)
            self.assertNotIn(public, ZIP_FILES)
            self.assertNotIn(public, ENCLOSURE_ZIP_FILES)


if __name__ == "__main__":
    unittest.main()
