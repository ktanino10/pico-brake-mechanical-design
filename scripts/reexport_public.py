"""Re-export the distributed single-axis native using public files only."""
from pathlib import Path
import argparse
import json
import tempfile

import FreeCAD as App
import Import

from build_cad import assert_shape, bounds, mesh_payload, normalized_step, readback, reference_interface_checks, shape_centroid
from geometry_contract import expected_instances, require_pose
from public_policy import ALLOWED, REFERENCES, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, default=ROOT / "downloads/brake-single.FCStd")
    parser.add_argument("--output", type=Path, required=True, help="A new, nonexistent output directory")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Choose a new output directory; existing data is not overwritten")
    catalog = json.loads((ROOT / "data/assembly.json").read_text())
    allowed = set(ALLOWED) | set(REFERENCES)
    if {part["id"] for part in catalog["parts"]} != allowed:
        raise ValueError("Public catalog is not the reviewed composition")
    document = App.openDocument(str(args.native.resolve()))
    try:
        if any(obj.TypeId not in {"Part::Feature", "App::DocumentObjectGroup"} for obj in document.Objects):
            raise ValueError("Unsupported native feature/dependency")
        objects = [obj for obj in document.Objects if obj.TypeId == "Part::Feature"]
        if {obj.Name for obj in objects} != {"Z_" + name for name in allowed} or len(objects) != len(allowed):
            raise ValueError("Use the distributed single-axis native, not a whole private assembly")
        shapes = {}
        expected = expected_instances(catalog["parts"], ("Z",))
        for obj in objects:
            if obj.OutList or obj.PhysicalQualified or obj.IsReference != (obj.PublicPartId in REFERENCES):
                raise ValueError("Unsupported native links or qualification")
            assert_shape(obj.Shape, obj.Name)
            require_pose(bounds(obj.Shape), shape_centroid(obj.Shape), expected[obj.Name], obj.Name)
            shapes[obj.PublicPartId] = obj.Shape.copy()
        interfaces = reference_interface_checks(shapes)
        meshes, mesh_report = mesh_payload(shapes, catalog["parts"], compare_existing=True)
        with tempfile.TemporaryDirectory(prefix="public-reexport-") as directory:
            raw_step = Path(directory) / "single.step"
            Import.export(objects, str(raw_step))
            args.output.mkdir(parents=True)
            output_step = args.output / "brake-single.step"
            normalized_step(raw_step, output_step)
    finally:
        App.closeDocument(document.Name)
    report = readback(args.native.resolve(), output_step.resolve(), expected)
    (args.output / "meshes.json").write_text(json.dumps(meshes, separators=(",", ":"), allow_nan=False) + "\n")
    (args.output / "reexport-check.json").write_text(json.dumps({
        "status": "PASS", "public_files_only": True, "parts": len(shapes),
        "step": report, "mesh": mesh_report, "reference_interfaces": interfaces, "physical_ready": False,
    }, indent=2) + "\n")
    print(f"Public-only re-export: {len(shapes)} parts; STEP and mesh readback passed.")


if __name__ == "__main__":
    main()
