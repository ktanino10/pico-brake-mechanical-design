"""Verify one independently authored three-face corner, not a complete enclosure."""
from pathlib import Path
import argparse
import itertools
import json
import math
import tempfile

import FreeCAD as App
import Import
import Part

from build_cad import assert_shape, bounds, digest, normalized_native, normalized_step, readback, shape_centroid
from enclosure_geometry import (CORNER_FIXING, CORNER_INNER, FRAME_INNER, FRAME_OUTER,
                                THREAD_MAJOR, THREAD_MINOR, axis_vector, corner_slice, point_on_axis)
from geometry_contract import require_pose


def validate_joints(shapes, joints):
    seen = set()
    for joint in joints:
        for key in ("fastener", "clamped_part", "receiver"):
            if joint[key] not in shapes:
                raise ValueError("Missing physical joint counterpart: " + joint[key])
        if joint["fastener"] in seen or joint["engagement_mm"] <= 0 or joint["bottom_margin_mm"] <= 0:
            raise ValueError("Invalid fastener/joint definition")
        seen.add(joint["fastener"])


def analytical_bounds(name):
    if name == "E_CORNER_PPP":
        return [CORNER_INNER]*3 + [69.0]*3
    axis = "XYZ".index(name[-1])
    if "COUPON" in name:
        low, high = [50.0]*3, [62.6]*3
        low[axis], high[axis] = FRAME_INNER, FRAME_OUTER
    else:
        low, high = [CORNER_FIXING-3]*3, [CORNER_FIXING+3]*3
        low[axis], high[axis] = 58.0, 68.0
    return low + high


def verify_collisions(shapes, joints):
    thread_pairs = {frozenset((row["fastener"], row["receiver"])): (i, row) for i, row in enumerate(joints)}
    positive = []
    for first, second in itertools.combinations(shapes, 2):
        common = shapes[first].common(shapes[second])
        volume = abs(common.Volume)
        if volume <= 1e-6:
            continue
        allowed = thread_pairs.get(frozenset((first, second)))
        if allowed is None:
            raise ValueError(f"Undeclared positive intersection: {first}/{second}: {volume}")
        axis, row = allowed
        mask = Part.makeCylinder(THREAD_MAJOR+1e-6, row["engagement_mm"]+2e-6,
                                 point_on_axis(axis, FRAME_INNER+1e-6, CORNER_FIXING), axis_vector(axis, -1))
        outside = abs(common.cut(mask).Volume)
        maximum = math.pi*(THREAD_MAJOR**2-THREAD_MINOR**2)*row["engagement_mm"]
        if outside > 1e-6 or volume > maximum+1e-5:
            raise ValueError("Intersection exceeds the declared local thread representation")
        positive.append({"a": first, "b": second, "volume_mm3": volume, "type": "bounded_major_minor_thread",
                         "outside_thread_mask_mm3": outside, "upper_volume_mm3": maximum})
    contacts = []
    for row in joints:
        for first, second, role in [(row["clamped_part"], row["receiver"], "frame-to-corner seat"),
                                    (row["fastener"], row["clamped_part"], "flat-head conical seat")]:
            distance = shapes[first].distToShape(shapes[second])[0]
            contact_area = 0.0
            for left in shapes[first].Faces:
                a = bounds(left)
                for right in shapes[second].Faces:
                    b = bounds(right)
                    if any(a[i] > b[i+3]+1e-7 or b[i] > a[i+3]+1e-7 for i in range(3)):
                        continue
                    if left.distToShape(right)[0] < 1e-7:
                        contact_area += left.common(right).Area
            if distance > 1e-6 or contact_area <= 1:
                raise ValueError("A required physical bearing/seat contact is absent")
            contacts.append({"a": first, "b": second, "role": role, "distance_mm": distance,
                             "common_surface_area_mm2": contact_area})
    return {"undeclared_positive_intersections": 0, "bounded_threads": positive, "intentional_contacts": contacts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new private slice output directory")
    shapes, joints = corner_slice()
    validate_joints(shapes, joints)
    expected = {}
    for name, shape in shapes.items():
        assert_shape(shape, name)
        box = analytical_bounds(name)
        if max(abs(a-b) for a,b in zip(bounds(shape),box)) > 1e-6:
            raise ValueError("Primitive shape departed from its independent dimension contract")
        expected[name] = {"bbox_mm": box, "center_of_mass_mm": shape_centroid(shape),
                          "volume_mm3": shape.Volume, "solid_count": len(shape.Solids), "is_reference": False}
    collision = verify_collisions(shapes, joints)
    try:
        validate_joints(shapes, [dict(joints[0], receiver="MISSING_RECEIVER")])
    except ValueError:
        missing_rejected = True
    else:
        raise ValueError("Missing-mate negative control passed")
    args.output.mkdir(parents=True)
    native, step = args.output/"corner-slice.FCStd", args.output/"corner-slice.step"
    with tempfile.TemporaryDirectory(prefix="independent-corner-") as directory:
        raw = Path(directory)
        doc = App.newDocument("IndependentCornerSlice")
        doc.CreatedBy = ""
        doc.Comment = "Independent nominal metal corner proof only; not full enclosure or fabrication approval."
        objects = []
        for name, shape in shapes.items():
            obj = doc.addObject("Part::Feature", name)
            obj.Label = name
            obj.Shape = shape.copy()
            obj.addProperty("App::PropertyBool", "IsReference"); obj.IsReference = False
            obj.addProperty("App::PropertyBool", "PhysicalQualified"); obj.PhysicalQualified = False
            obj.addProperty("App::PropertyString", "GeometryOrigin"); obj.GeometryOrigin = "new-independent-primitives"
            objects.append(obj)
        doc.recompute()
        doc.saveAs(str(raw/"slice.FCStd")); Import.export(objects, str(raw/"slice.step"))
        App.closeDocument(doc.Name)
        normalized_native(raw/"slice.FCStd", native); normalized_step(raw/"slice.step", step)
    saved = readback(native, step, expected)
    before = digest(native)
    doc = App.openDocument(str(native))
    try:
        obj = doc.getObject("E_COUPON_X")
        placement = obj.Placement
        placement.Base += App.Vector(.25, 0, 0)
        obj.Placement = placement
        try:
            require_pose(bounds(obj.Shape), shape_centroid(obj.Shape), expected[obj.Name], obj.Name)
        except ValueError:
            pose_rejected = True
        else:
            raise ValueError("Wrong-pose negative control passed")
    finally:
        App.closeDocument(doc.Name)
    if digest(native) != before:
        raise ValueError("Negative pose check modified saved output")
    report = {"status": "PASS", "cad_slice_complete": True, "full_enclosure_complete": False,
              "parts": expected, "joints": joints, "geometry": collision, "readback": saved,
              "negative_controls": {"missing_mate_rejected": missing_rejected, "wrong_pose_rejected": pose_rejected},
              "source_geometry_read": False, "whole_fit": False, "build_ready": False, "physical_ready": False}
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":"PASS","parts":len(shapes),"joints":len(joints),
                      "bounded_threads":len(collision["bounded_threads"]),
                      "intentional_contacts":len(collision["intentional_contacts"]),
                      "native_sha256":digest(native),"step_sha256":digest(step)},indent=2))


if __name__ == "__main__":
    main()
