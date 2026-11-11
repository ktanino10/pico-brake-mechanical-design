"""Extract only reviewed authored C08 shapes, then make independent public documents."""
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json
import math
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET

import FreeCAD as App
import Import
import MeshPart
import Part

from catalog import JOINTS, make_catalog
from geometry_contract import expected_instances, mesh_moments, require_pose
from public_policy import ALLOWED, REFERENCES, ROOT, SOURCE_SHA256, validate_request

FLAGS = {"whole_fit": False, "build_ready": False, "physical_ready": False}
AXIS_ROTATIONS = {
    "Z": App.Rotation(),
    "X": App.Rotation(App.Vector(0, 0, 1), App.Vector(1, 0, 0)).multiply(
        App.Rotation(App.Vector(0, 0, 1), 180)),
    "Y": App.Rotation(App.Vector(0, 0, 1), App.Vector(0, 1, 0)),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(shape):
    box = shape.optimalBoundingBox(False, False)
    return [box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax]


def shape_centroid(shape):
    solids = shape.Solids
    if not solids:
        raise ValueError("A volume centroid requires solids")
    total = math.fsum(solid.Volume for solid in solids)
    if total <= 0:
        raise ValueError("A volume centroid requires positive volume")
    return [math.fsum(solid.Volume * list(solid.CenterOfMass)[i] for solid in solids) / total for i in range(3)]


def cylinder(radius, front, length, x=0, y=0):
    return Part.makeCylinder(radius, length, App.Vector(x, y, front))


def ring(outer, inner, front, length):
    return cylinder(outer, front, length).cut(cylinder(inner, front - 1, length + 2))


def position(radius, degrees):
    angle = math.radians(degrees)
    return radius * math.cos(angle), radius * math.sin(angle)


def rotate(shape, angle):
    result = shape.copy()
    result.rotate(App.Vector(), App.Vector(0, 0, 1), angle)
    return result


def references():
    wheel = ring(58, 14.2, -68, 3.2).cut(cylinder(27.1, -68.1, 1.6))
    for angle in (45, 105, 225, 285):
        xy = position(19, angle)
        wheel = wheel.cut(cylinder(1.7, -69, 6, *xy))
    for angle in (0, 120, 240):
        for y in (0.75, 5.25):
            hole = cylinder(1.05, -69, 6, 24, y)
            wheel = wheel.cut(rotate(hole, angle))
        window = Part.makeBox(7.4, 9.6, 6, App.Vector(20.3, 28.2, -69))
        wheel = wheel.cut(rotate(window, angle))
    for angle in range(0, 360, 45):
        xy = position(52.75, angle)
        wheel = wheel.cut(cylinder(2.2, -69, 6, *xy))
        wheel = wheel.cut(Part.makeCone(4, 2, 2.3, App.Vector(*xy, -68)))
    for angle in (0, 180):
        wheel = wheel.cut(cylinder(1.5, -66.51, 1.51, *position(17, angle)))
    for angle in (100, 220, 340):
        wheel = wheel.cut(cylinder(0.8, -67.8, 3.1, *position(43, angle)))
    frame = ring(69, 60, -68, 5.2)
    for angle in (45, 135, 225, 315):
        xy = position(63, angle)
        frame = frame.cut(cylinder(1.7, -69, 8, *xy))
        frame = frame.cut(Part.makeCone(3, 1.5, 1.7, App.Vector(*xy, -68)))
        frame = frame.cut(cylinder(2.025, -63.85, 1.06, *xy))
    shaft = cylinder(3, -67.5, 12.5).cut(
        Part.makeCylinder(1, 30, App.Vector(-15, 0, -65.05), App.Vector(1, 0, 0)))
    return {
        "REF_WHEEL": wheel, "REF_FRAME": frame,
        "REF_MOTOR_ENVELOPE": cylinder(14, -55, 22), "REF_SHAFT": shaft,
    }


def reference_interface_checks(shapes):
    rows = []
    patterns = (
        ("FRAME_BOLT", "REF_FRAME", 63, (45, 135, 225, 315)),
        ("WHEEL_BOLT", "REF_WHEEL", 19, (45, 105, 225, 285)),
        ("RIM_BOLT", "REF_WHEEL", 52.75, tuple(range(0, 360, 45))),
    )
    for prefix, reference, radius, angles in patterns:
        for i, angle in enumerate(angles):
            name = f"{prefix}_{i}"
            bb = bounds(shapes[name])
            actual_center = [(bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2]
            nominal = position(radius, angle)
            center_error = math.dist(actual_center, nominal)
            intrusion = abs(shapes[reference].common(shapes[name]).Volume)
            if center_error > 1e-5 or intrusion > 1e-5:
                raise ValueError(f"Reference hole/fastener mismatch: {name}")
            rows.append({"part": name, "reference": reference, "axis_center_error_mm": center_error,
                         "undeclared_common_mm3": intrusion})
    for name in [*(f"SPRING_ROOT_BOLT_{i}" for i in range(6)),
                 *(f"SPRING_TIP_NUT_PLATE_{i}" for i in range(3)), "HUB_FACE", "HUB"]:
        intrusion = abs(shapes["REF_WHEEL"].common(shapes[name]).Volume)
        if intrusion > 1e-5:
            raise ValueError(f"Reference counterbore/window mismatch: {name}")
        rows.append({"part": name, "reference": "REF_WHEEL", "undeclared_common_mm3": intrusion})
    for i in range(4):
        name = f"POST_{i}"
        intrusion = abs(shapes["REF_FRAME"].common(shapes[name]).Volume)
        if intrusion > 1e-5:
            raise ValueError(f"Reference frame post pocket mismatch: {name}")
        rows.append({"part": name, "reference": "REF_FRAME", "undeclared_common_mm3": intrusion})
    return {
        "scope": "Nominal public-reference hole, counterbore and window correspondence only; no physical fit, torque or tool-path approval.",
        "checks": rows, "motor_interface_qualified": False,
        "whole_fit": False, "build_ready": False, "physical_ready": False,
    }


def normalized_native(source, target):
    """Repack only a newly constructed document, never a private source archive."""
    with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as outgoing:
        for entry in incoming.infolist():
            if "/" in entry.filename or entry.filename.startswith("."):
                raise ValueError("Unexpected native archive member")
            data = incoming.read(entry)
            if entry.filename in {"Document.xml", "GuiDocument.xml"}:
                tree = ET.fromstring(data)
                for prop in tree.iter("Property"):
                    if prop.get("name") in {"CreatedBy", "LastModifiedBy", "Company", "FileName",
                                             "CreationDate", "LastModifiedDate", "TransientDir"}:
                        for item in prop:
                            if "value" in item.attrib:
                                item.set("value", "")
                    if prop.get("name") == "Uid":
                        for item in prop:
                            if "value" in item.attrib:
                                item.set("value", "00000000-0000-0000-0000-000000000000")
                for properties in tree.iter("Properties"):
                    defaults = [prop for prop in properties if prop.get("name") == "ShapeMaterial"]
                    for prop in defaults:
                        properties.remove(prop)
                    if defaults:
                        properties.set("Count", str(int(properties.get("Count")) - len(defaults)))
                data = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
            info = zipfile.ZipInfo(entry.filename, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            outgoing.writestr(info, data)


def normalized_step(source, target):
    text = source.read_text()
    replacement = (
        "FILE_NAME('public-brake.step','2026-11-11T00:00:00',(''),(''),"
        "'Open CASCADE','FreeCAD','');"
    )
    text, count = re.subn(r"FILE_NAME\s*\(.*?\)\s*;", lambda _: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise ValueError("Missing or ambiguous STEP header")
    target.write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n")


def assert_shape(shape, name):
    if shape.isNull() or not shape.isValid() or not shape.Solids or shape.Volume <= 0:
        raise ValueError(f"Invalid solid: {name}")


def make_document(shapes, parts, axes, native, step, temporary):
    document = App.newDocument("PublicBrake" + str(len(axes)) + "Axis")
    document.Label = "Public brake / reference fixture"
    document.CreatedBy = ""
    document.Comment = "Editable shape/placement snapshot. Independent reference fixture. Not fabrication-ready."
    objects = []
    expected = expected_instances(parts, axes)
    for axis in axes:
        group = document.addObject("App::DocumentObjectGroup", "Axis_" + axis)
        group.Label = axis + " / reference layout" if len(axes) > 1 else "Z / public module"
        for part in parts:
            identifier = axis + "_" + part["id"]
            obj = document.addObject("Part::Feature", identifier)
            obj.Label = identifier
            obj.Shape = shapes[part["id"]].copy()
            obj.Placement = App.Placement(App.Vector(), AXIS_ROTATIONS[axis]).multiply(obj.Placement)
            for key, value in {
                "PublicPartId": part["id"], "JapaneseName": part["label"],
                "Provenance": part["provenance"], "MaterialCandidate": part["material"],
                "Role": part["role"],
            }.items():
                obj.addProperty("App::PropertyString", key, "Public assembly")
                setattr(obj, key, value)
            for key, value in {"IsReference": part["is_reference"], "PhysicalQualified": False}.items():
                obj.addProperty("App::PropertyBool", key, "Public assembly")
                setattr(obj, key, value)
            group.addObject(obj)
            objects.append(obj)
    document.recompute()
    raw_native = temporary / (native.stem + ".FCStd")
    raw_step = temporary / (step.stem + ".step")
    document.saveAs(str(raw_native))
    Import.export(objects, str(raw_step))
    App.closeDocument(document.Name)
    normalized_native(raw_native, native)
    normalized_step(raw_step, step)
    return expected


def readback(native, step, expected):
    document = App.openDocument(str(native))
    native_bounds_error, native_center_error = 0.0, 0.0
    try:
        if any(obj.TypeId not in {"Part::Feature", "App::DocumentObjectGroup"} for obj in document.Objects):
            raise ValueError("Unexpected public native object type")
        objects = [obj for obj in document.Objects if obj.TypeId == "Part::Feature"]
        if {obj.Name for obj in objects} != set(expected):
            raise ValueError("Native part names/count mismatch")
        for obj in objects:
            assert_shape(obj.Shape, obj.Name)
            row = expected[obj.Name]
            if abs(obj.Shape.Volume - row["volume_mm3"]) > 1e-5:
                raise ValueError(f"Native volume mismatch: {obj.Name}")
            bbox_error, centroid_error = require_pose(
                bounds(obj.Shape), shape_centroid(obj.Shape), row, obj.Name)
            native_bounds_error = max(native_bounds_error, bbox_error)
            native_center_error = max(native_center_error, centroid_error)
            if obj.InList and any(o.TypeId != "App::DocumentObjectGroup" for o in obj.InList):
                raise ValueError("Native contains a non-group dependency")
            if obj.OutList or obj.TypeId != "Part::Feature":
                raise ValueError("Public native must contain independent shapes")
            if obj.IsReference != row["is_reference"] or obj.PhysicalQualified:
                raise ValueError("Qualification/reference labels changed")
    finally:
        App.closeDocument(document.Name)
    document = App.newDocument("PublicStepReadback")
    try:
        Import.insert(str(step), document.Name)
        objects = [obj for obj in document.Objects if hasattr(obj, "Shape") and obj.Shape.Solids]
        # STEP import can add aggregate assembly objects. Only labelled leaves count.
        leaves = [obj for obj in objects if obj.Label in expected]
        if len(leaves) != len(expected) or {obj.Label for obj in leaves} != set(expected):
            raise ValueError(f"STEP part labels/count mismatch: {len(leaves)} != {len(expected)}")
        max_volume_error = 0.0
        max_relative_volume_error = 0.0
        max_bounds_error = 0.0
        max_center_error = 0.0
        boolean_checks = []
        for obj in leaves:
            assert_shape(obj.Shape, obj.Label)
            row = expected[obj.Label]
            volume_error = abs(obj.Shape.Volume - row["volume_mm3"])
            bound_error = max(abs(a - b) for a, b in zip(bounds(obj.Shape), row["bbox_mm"]))
            center_error = math.dist(shape_centroid(obj.Shape), row["center_of_mass_mm"])
            max_volume_error = max(max_volume_error, volume_error)
            max_relative_volume_error = max(max_relative_volume_error, volume_error / row["volume_mm3"])
            max_bounds_error = max(max_bounds_error, bound_error)
            max_center_error = max(max_center_error, center_error)
            if len(obj.Shape.Solids) != row["solid_count"] or volume_error > max(1e-4, row["volume_mm3"] * 1e-4) or bound_error > 0.001 or center_error > 0.01:
                raise ValueError(f"STEP readback differs: {obj.Label}")
            if volume_error > max(1e-4, row["volume_mm3"] * 1e-7):
                native_doc = App.openDocument(str(native))
                try:
                    original = native_doc.getObject(obj.Label).Shape
                    missing = abs(original.cut(obj.Shape).Volume)
                    extra = abs(obj.Shape.cut(original).Volume)
                    if missing + extra > 1e-5:
                        raise ValueError(f"STEP changed material geometry: {obj.Label}")
                    boolean_checks.append({"part": obj.Label, "native_minus_step_mm3": missing,
                                           "step_minus_native_mm3": extra})
                finally:
                    App.closeDocument(native_doc.Name)
        actual_solid_count = sum(len(obj.Shape.Solids) for obj in leaves)
    finally:
        App.closeDocument(document.Name)
    return {
        "parts": len(expected), "solids": actual_solid_count, "valid_solids": True,
        "reference_parts": sum(row["is_reference"] for row in expected.values()),
        "native_independent_features": True, "step_named_parts_match": True,
        "expected_pose_basis": "Pre-document canonical Z exact geometric bbox/centroid plus independently coded X=(z,-y,x), Y=(x,z,-y), Z=(x,y,z)",
        "bounds_method": "optimalBoundingBox(useTriangulation=False,useShapeTolerance=False)",
        "max_native_world_bounds_error_mm": native_bounds_error,
        "max_native_world_centroid_error_mm": native_center_error,
        "max_step_volume_error_mm3": max_volume_error,
        "max_step_relative_volume_error": max_relative_volume_error,
        "max_step_bounds_error_mm": max_bounds_error,
        "max_step_centroid_error_mm": max_center_error,
        "step_tolerances": {"relative_integrated_volume": 0.0001, "bounds_mm": 0.001, "centroid_mm": 0.01},
        "boolean_checks_for_integration_differences": boolean_checks,
        "files": [{"path": "downloads/" + path.name, "sha256": digest(path), "bytes": path.stat().st_size}
                  for path in (native, step)],
    }


def mesh_payload(shapes, parts, compare_existing=False):
    meshes, max_error, max_bounds_error = [], 0.0, 0.0
    max_centroid_error, reexport_bounds_error, reexport_centroid_error = 0.0, 0.0, 0.0
    for part in parts:
        shape = shapes[part["id"]]
        mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.045, AngularDeflection=0.16, Relative=False)
        points, facets = mesh.Topology
        vertices = [[round(point.x, 6), round(point.y, 6), round(point.z, 6)] for point in points]
        indices = [list(face) for face in facets]
        volume, centroid = mesh_moments(vertices, indices)
        volume_error = abs(volume - shape.Volume) / shape.Volume
        bb = [min(v[i] for v in vertices) for i in range(3)] + [max(v[i] for v in vertices) for i in range(3)]
        bbox_error = max(abs(a - b) for a, b in zip(bb, bounds(shape)))
        centroid_error = math.dist(centroid, shape_centroid(shape))
        if volume_error > 0.02 or bbox_error > 0.12 or centroid_error > 0.02:
            raise ValueError(f"Mesh/CAD mismatch: {part['id']} volume={volume_error} bounds={bbox_error}")
        if compare_existing:
            require_pose(bounds(shape), shape_centroid(shape), part, part["id"])
            rb = max(abs(a - b) for a, b in zip(bb, part["mesh_bbox_mm"]))
            rc = math.dist(centroid, part["mesh_centroid_mm"])
            if rb > 0.002 or rc > 0.002:
                raise ValueError(f"Re-exported mesh differs from published mesh moments: {part['id']}")
            reexport_bounds_error = max(reexport_bounds_error, rb)
            reexport_centroid_error = max(reexport_centroid_error, rc)
        max_error = max(max_error, volume_error)
        max_bounds_error = max(max_bounds_error, bbox_error)
        max_centroid_error = max(max_centroid_error, centroid_error)
        if not compare_existing:
            part.update({
                "volume_mm3": shape.Volume, "bbox_mm": bounds(shape), "solid_count": len(shape.Solids),
                "center_of_mass_mm": shape_centroid(shape), "mesh_bbox_mm": bb, "mesh_centroid_mm": centroid,
            })
        meshes.append({"id": part["id"], "positions": [v for vertex in vertices for v in vertex],
                       "indices": [v for face in indices for v in face]})
    return {"schema": "public-brake-mesh-v1", "units": "mm", "parts": meshes}, {
        "parts": len(meshes), "triangles": sum(len(m["indices"]) // 3 for m in meshes),
        "max_relative_volume_error": max_error, "max_bounds_error_mm": max_bounds_error,
        "max_centroid_error_mm": max_centroid_error,
        "volume_tolerance": 0.02, "bounds_tolerance_mm": 0.12, "centroid_tolerance_mm": 0.02,
        "compared_to_published_mesh_moments": compare_existing,
        "max_reexport_mesh_bounds_error_mm": reexport_bounds_error,
        "max_reexport_mesh_centroid_error_mm": reexport_centroid_error,
    }


def pose_negative_control(native, parts):
    before = digest(native)
    expected = expected_instances(parts, ("Z",))
    document = App.openDocument(str(native))
    try:
        obj = document.getObject("Z_SPRING_1")
        obj.Placement = App.Placement(App.Vector(), App.Rotation(App.Vector(0, 0, 1), 3)).multiply(obj.Placement)
        try:
            require_pose(bounds(obj.Shape), shape_centroid(obj.Shape), expected[obj.Name], obj.Name)
        except ValueError as error:
            if "Independent world pose mismatch" not in str(error):
                raise
        else:
            raise ValueError("A deliberately misoriented part passed the world-pose check")
    finally:
        App.closeDocument(document.Name)
    if digest(native) != before:
        raise ValueError("Negative pose test changed the public native")
    return {"part": "Z_SPRING_1", "extra_rotation_deg": 3, "result": "REJECTED",
            "tested_in_memory_only": True, "native_unchanged": True}


def export_tables(parts):
    with (ROOT / "data/parts.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["part_id", "部品", "区分", "参照部材", "材質候補", "単軸個数", "参考三軸個数", "体積mm3", "provenance"])
        for row in parts:
            writer.writerow([row["id"], row["label"], row["role"], str(row["is_reference"]).lower(),
                             row["material"], 1, 3, f"{row['volume_mm3']:.6f}", row["provenance"]])
    with (ROOT / "data/joints.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["instance_id", "joint_id", "接合", "ねじ", "C08条件付き計算Nm", "相手部品ID",
                         "相手材", "参考部材を含む", "適用限界"])
        for row in parts:
            if not row["is_fastener"]:
                continue
            item = JOINTS[row["joint_id"]]
            torque = "未決" if item["torque_Nm"] is None else "–".join(str(v) for v in item["torque_Nm"])
            writer.writerow(["Z_" + row["id"], row["joint_id"], item["title"], item["size"], torque,
                             ";".join("Z_" + mate for mate in row["mates"]), item["receiver"],
                             str(row["reference_joint"]).lower(), item["conditions"]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    if source.is_relative_to(ROOT):
        raise ValueError("Private input must not be copied into the public worktree")
    before = digest(source)
    if before != SOURCE_SHA256:
        raise ValueError("Only the reviewed C08 native is allowed")
    policy = json.loads((ROOT / "data/provenance.json").read_text())
    if {r["public_part"] for r in policy["included"]} != set(ALLOWED) | set(REFERENCES):
        raise ValueError("Published provenance is stale")
    validate_request(ALLOWED)
    document = App.openDocument(str(source))
    shapes, materials = {}, {}
    try:
        for name in ALLOWED:
            obj = document.getObject("Z_" + name)
            if obj is None or obj.Role in {"source-modified", "source-context"}:
                raise ValueError("Disallowed or missing source object: " + name)
            shapes[name] = obj.Shape.copy()
            materials[name] = obj.MaterialCandidate
    finally:
        App.closeDocument(document.Name)
    shapes.update(references())
    for name, shape in shapes.items():
        assert_shape(shape, name)
    interface_report = reference_interface_checks(shapes)
    parts = make_catalog(materials)
    mesh, mesh_report = mesh_payload(shapes, parts)
    downloads = ROOT / "downloads"
    downloads.mkdir(exist_ok=True)
    reports = {}
    with tempfile.TemporaryDirectory(prefix="public-brake-") as directory:
        temporary = Path(directory)
        for mode, axes in (("single", ("Z",)), ("reference-three", ("Z", "X", "Y"))):
            native = downloads / f"brake-{mode}.FCStd"
            step = downloads / f"brake-{mode}.step"
            expected = make_document(shapes, parts, axes, native, step, temporary)
            reports[mode] = readback(native, step, expected)
    pose_negative = pose_negative_control(downloads / "brake-single.FCStd", parts)
    if digest(source) != before:
        raise ValueError("Protected C08 input changed")
    mesh_path = ROOT / "data/meshes.json"
    mesh_path.write_text(json.dumps(mesh, separators=(",", ":"), allow_nan=False) + "\n")
    assembly = {
        "schema": "public-brake-assembly-v1", "units": "mm", "revision": "C08-public-1",
        "reference_fixture": True, **FLAGS, "parts": parts, "joints": JOINTS,
        "mesh": {"path": "data/meshes.json", "sha256": digest(mesh_path), "parts": len(parts)},
        "axis_quaternions_xyzw": {axis: list(rotation.Q) for axis, rotation in AXIS_ROTATIONS.items()},
        "scope": "Authored C08 brake parts plus independent reference primitives; not the source Pico assembly.",
        "known_limits": {
            "three_axis_max_current_A": 1.756857856781656, "retained_current_limit_A": 1.5,
            "inner_edge_force_N": 500.034, "structure_case_N": 500,
            "inner_edge_required_A": 0.330350651, "hot_available_A": 0.321827745,
            "coil_turns": 796, "nominal_stroke_mm": 0.2,
            "actual_motor_compatible": False, "magnetic_thermal_friction_fatigue_qualified": False,
            "source_whole_machine_mass_and_fit_transferred": False,
        },
    }
    (ROOT / "data/assembly.json").write_text(json.dumps(assembly, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    export_tables(parts)
    report = {
        "schema": "public-brake-cad-validation-v1", "status": "PASS",
        "source_sha256": SOURCE_SHA256, "source_unchanged": True, "source_document_copied": False,
        "freecad_version": ".".join(App.Version()[:3]), "units": "mm",
        "native_editability": "Independent Part::Feature shapes and placements; not a full parametric design history.",
        "documents": reports, "mesh": mesh_report, "reference_interfaces": interface_report,
        "pose_negative_control": pose_negative, **FLAGS,
        "scope": "Digital public-package consistency only, not whole-machine or physical validation.",
    }
    (ROOT / "validation").mkdir(exist_ok=True)
    (ROOT / "validation/cad.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"public_parts": len(parts), "documents": reports, "mesh": mesh_report, "source_unchanged": True}, indent=2))


if __name__ == "__main__":
    main()
