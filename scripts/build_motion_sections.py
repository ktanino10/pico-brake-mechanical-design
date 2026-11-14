"""Derive a closed contact-region slice from the unchanged public C08 native."""
from pathlib import Path
import hashlib
import json

import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("ARMATURE", "YOKE", "WINDING", "BOBBIN", "COIL_RETAINER",
         "POLE_CAP_INNER", "POLE_CAP_OUTER", "REF_WHEEL", "LINING_0", "LINING_1", "LINING_2")


def main():
    source = ROOT / "downloads/brake-single.FCStd"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    document = App.openDocument(str(source))
    items = []
    try:
        slab = Part.makeBox(1.2, 8, 30, App.Vector(-.6, 32, -72))
        for name in NAMES:
            shape = document.getObject("Z_" + name).Shape.common(slab)
            if shape.Volume < 1e-7:
                continue
            vertices, faces = shape.tessellate(.10)
            items.append({"id": name, "positions": [v for point in vertices for v in point],
                          "indices": [v for face in faces for v in face]})
    finally:
        App.closeDocument(document.Name)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    result = {"schema": "public-c08-motion-section-v1", "units": "mm", "physical_ready": False,
              "source_native_sha256": before,
              "source_mesh_sha256": json.loads((ROOT / "data/assembly.json").read_text())["mesh"]["sha256"],
              "slice": {"x_mm": [-.6, .6], "y_mm": [32, 40], "z_mm": [-72, -42]},
              "gap_mm": .2, "parts": items}
    (ROOT / "data/motion-section.json").write_text(json.dumps(result, separators=(",", ":")) + "\n")
    print(f"Derived {len(items)} contact-slice meshes; public C08 native unchanged.")


if __name__ == "__main__":
    main()
