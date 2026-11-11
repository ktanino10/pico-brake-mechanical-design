"""Verify independent enclosure CAD slices without claiming complete hardware fit."""
from pathlib import Path
import argparse
import copy
import itertools
import json
import math
import re
import tempfile

import FreeCAD as App
import Import
import Part

from build_cad import assert_shape, bounds, digest, normalized_native, normalized_step, readback, shape_centroid
from enclosure_geometry import (CORNER_FIXING, CORNER_INNER, FRAME_INNER, FRAME_OUTER,
                                THREAD_MAJOR, THREAD_MINOR, case_point, corner_cap_positive, corner_positive,
                                corner_slice, frame_cage)
from geometry_contract import require_pose


def validate_joints(shapes, joints):
    seen, seen_ids = set(), set()
    for joint in joints:
        for key in ("fastener", "clamped_part", "receiver"):
            if joint[key] not in shapes:
                raise ValueError("Missing physical joint counterpart: " + joint[key])
        end = joint.get("receiver_end", "blind")
        if (joint["fastener"] in seen or joint["id"] in seen_ids or joint["engagement_mm"] <= 0 or
                end not in ("blind", "through")):
            raise ValueError("Invalid fastener/joint definition")
        if ((end == "blind" and (joint["bottom_margin_mm"] is None or joint["bottom_margin_mm"] <= 0)) or
                (end == "through" and (joint["bottom_margin_mm"] is not None or joint["protrusion_mm"] < 0))):
            raise ValueError("Invalid blind/through receiving end condition")
        if not 0 < joint["thread_minor_radius_mm"] < joint["thread_major_radius_mm"]:
            raise ValueError("Invalid declared thread radii")
        stack = joint.get("stack", [joint["clamped_part"], joint["receiver"]])
        if (not stack or stack[0] != joint["clamped_part"] or stack[-1] != joint["receiver"] or
                len(set(stack)) != len(stack) or joint["fastener"] in stack):
            raise ValueError("Invalid ordered clamped stack: "+joint["id"])
        if any(name not in shapes for name in stack):
            raise ValueError("Missing physical stack member: "+joint["id"])
        if abs(math.hypot(*joint["axis"])-1) > 1e-8:
            raise ValueError("The nominal fastener axis must be a unit vector")
        seen.add(joint["fastener"])
        seen_ids.add(joint["id"])


def verify_fastener_lengths(shapes, joints):
    results = []
    for row in joints:
        convention, nominal = row["length_convention"], row["nominal_length_mm"]
        if convention not in ("including-head", "under-head") or nominal <= 0:
            raise ValueError("Unknown nominal screw length convention")
        head = row["head_height_mm"] if convention == "under-head" else 0
        axis, seat = App.Vector(*row["axis"]), App.Vector(*row["seat_point_mm"])
        axial = [(vertex.Point-seat).dot(axis) for vertex in shapes[row["fastener"]].Vertexes]
        measured = [min(axial), max(axial)]
        if (max(abs(measured[0]+head), abs(measured[1]-nominal)) > 1e-6 or
                abs(row["modeled_total_length_mm"]-(measured[1]-measured[0])) > 1e-6):
            raise ValueError("Fastener axial length disagrees with its convention: "+row["fastener"])
        results.append({"fastener":row["fastener"],"length_convention":convention,
                        "nominal_length_mm":nominal,"measured_axis_extent_mm":measured,
                        "measured_total_length_mm":measured[1]-measured[0]})
    return results


def verify_holder_conditions(shapes, joints, base_details):
    from enclosure_holders import N, holders
    path = Path(__file__).resolve().parents[1]/"data/enclosure-nominal-conditions.json"
    conditions = json.loads(path.read_text())
    altered = copy.deepcopy(conditions)
    altered["pcb"]["nominal_board_thickness_mm"] = 2.0
    extra, changed_joints, changed_details = holders(altered)
    changed = dict(shapes)
    changed.update(extra)
    joint_set = [row for row in joints if not row["id"].startswith("EH_")]+changed_joints
    validate_joints(changed, joint_set)
    lengths = verify_fastener_lengths(changed, joint_set)
    collision = verify_collisions(changed, joint_set)
    coordinates = [vertex.Point.dot(N) for vertex in changed["E_REF_BOARD_PCB"].Vertexes]
    thickness = max(coordinates)-min(coordinates)
    pcb_rows = [row for row in changed_joints if row["id"].startswith("EH_BOARD_PCB_")]
    if (abs(thickness-2) > 1e-6 or len(pcb_rows) != 4 or
            any(abs(row["frame_grip_mm"]-5.5) > 1e-6 or abs(row["engagement_mm"]-4.5) > 1e-6 for row in pcb_rows)):
        raise ValueError("A changed board condition silently retained stale geometry or engagement")
    bad_length = dict(pcb_rows[0], modeled_total_length_mm=10)
    try:
        verify_fastener_lengths(changed, [bad_length])
    except ValueError:
        stale_length_rejected = True
    else:
        raise ValueError("A 13 mm modeled screw passed a 10 mm total-length declaration")
    bad_stack = dict(pcb_rows[0], stack=[pcb_rows[0]["clamped_part"],"MISSING_SPACER",pcb_rows[0]["receiver"]])
    try:
        validate_joints(changed, [bad_stack])
    except ValueError:
        missing_stack_rejected = True
    else:
        raise ValueError("A missing clamped-stack member passed")
    return {"conditions_sha256":digest(path),"base_details":base_details,"changed_variant_details":changed_details,
            "changed_board_thickness_mm":thickness,"changed_joint_grip_mm":pcb_rows[0]["frame_grip_mm"],
            "changed_joint_engagement_mm":pcb_rows[0]["engagement_mm"],
            "changed_variant_thread_checks":len(collision["declared_thread_presence"]),
            "changed_variant_length_checks":len(lengths),"stale_total_length_rejected":stale_length_rejected,
            "missing_stack_member_rejected":missing_stack_rejected,"mutant_not_saved_as_delivery":True}


def analytical_bounds(name):
    if name.startswith("E_CORNER_CAP_"):
        signs = [1 if letter == "P" else -1 for letter in name[-3:]]
        return [min(s*56, s*69) for s in signs] + [max(s*56, s*69) for s in signs]
    if name.startswith("E_CAP_SCREW_"):
        signs = [1 if letter == "P" else -1 for letter in name[-3:]]
        lo = 66 - 14/math.sqrt(3) - 1.5*math.sqrt(2/3)
        hi = 66 + 3*math.sqrt(2/3)
        return [min(s*lo, s*hi) for s in signs] + [max(s*lo, s*hi) for s in signs]
    if re.fullmatch(r"E_CORNER_[PN]{3}", name):
        signs = [1 if letter == "P" else -1 for letter in name[-3:]]
        return [min(s*CORNER_INNER, s*69) for s in signs] + [max(s*CORNER_INNER, s*69) for s in signs]
    if name.startswith(("E_FRAME_MOTOR_", "E_FRAME_BOARD_")):
        z0, z1 = (62.8, 68) if "BOARD" in name else (-68, -62.8)
        corners = [case_point(point, name[-1]) for point in itertools.product((-68, 68), (-62.6, 62.6), (z0, z1))]
        return [min(p[i] for p in corners) for i in range(3)] + [max(p[i] for p in corners) for i in range(3)]
    if name.startswith("E_FRAME_SCREW_"):
        signs = [1 if letter == "P" else -1 for letter in name.split("_")[-2]]
        axis = "XYZ".index(name[-1])
        low = [s*CORNER_FIXING-3 for s in signs]
        high = [s*CORNER_FIXING+3 for s in signs]
        low[axis], high[axis] = sorted((signs[axis]*58, signs[axis]*68))
        return low + high
    axis = "XYZ".index(name[-1])
    if "COUPON" in name:
        low, high = [50.0]*3, [62.6]*3
        low[axis], high[axis] = FRAME_INNER, FRAME_OUTER
    else:
        low, high = [CORNER_FIXING-3]*3, [CORNER_FIXING+3]*3
        low[axis], high[axis] = 58.0, 68.0
    return low + high


def verify_outer_surfaces(shapes):
    outer_faces, edges = [], []
    for name, shape in shapes.items():
        if not name.startswith("E_CORNER_CAP_"):
            continue
        signs = [1 if letter == "P" else -1 for letter in name[-3:]]
        for axis in range(3):
            area = sum(face.Area for face in shape.Faces
                       if abs(bounds(face)[axis]-signs[axis]*69) < 1e-6 and
                          abs(bounds(face)[axis+3]-signs[axis]*69) < 1e-6)
            if area < 60:
                raise ValueError("An outer corner face is absent or reduced to a pin/edge")
            outer_faces.append({"part": name, "axis": "XYZ"[axis], "coordinate_mm": signs[axis]*69, "area_mm2": area})
    for owner, second, variable in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
        for first_sign in (-1, 1):
            for second_sign in (-1, 1):
                low, sizes = [0.0]*3, [.2]*3
                low[owner] = 67.8 if first_sign > 0 else -68
                low[second] = 67.8 if second_sign > 0 else -68
                low[variable], sizes[variable] = -57, 114
                probe = Part.makeBox(*sizes, App.Vector(*low))
                name = "E_FRAME_"+("BOARD_" if first_sign > 0 else "MOTOR_")+"XYZ"[owner]
                volume = shapes[name].common(probe).Volume
                if volume < probe.Volume * .999:
                    raise ValueError("A required exterior frame-edge strip has missing material")
                edges.append({"part": name, "fixed_axes": ["XYZ"[owner], "XYZ"[second]],
                              "signs": [first_sign, second_sign], "covered_length_mm": 114, "probe_material_mm3": volume})
    if len(outer_faces) != 24 or len(edges) != 12:
        raise ValueError("Outer corner/edge coverage is incomplete")
    return {"outer_corner_faces": outer_faces, "frame_edge_strips": edges,
            "pin_or_screw_extents_are_not_used_as_coverage_evidence": True,
            "contact_strength_or_impact_safety_qualified": False}


def verify_thread_presence(shapes, joints):
    results = []
    for row in joints:
        expected = math.pi*(row["thread_major_radius_mm"]**2-row["thread_minor_radius_mm"]**2)*row["engagement_mm"]
        volume = abs(shapes[row["fastener"]].common(shapes[row["receiver"]]).Volume)
        minimum = expected-max(1e-5, expected*1e-6)
        if volume < minimum:
            raise ValueError("Nominal thread representation missing: "+row["id"])
        results.append({"joint": row["id"], "observed_mm3": volume,
                        "nominal_annulus_mm3": expected, "minimum_required_mm3": minimum})
    return results


def verify_collisions(shapes, joints):
    thread_pairs = {frozenset((row["fastener"], row["receiver"])): row for row in joints}
    boxes = {name: bounds(shape) for name, shape in shapes.items()}
    positive = []
    for first, second in itertools.combinations(shapes, 2):
        a, b = boxes[first], boxes[second]
        if any(a[i] > b[i+3]+1e-7 or b[i] > a[i+3]+1e-7 for i in range(3)):
            continue
        common = shapes[first].common(shapes[second])
        volume = abs(common.Volume)
        if volume <= 1e-6:
            continue
        allowed = thread_pairs.get(frozenset((first, second)))
        if allowed is None:
            raise ValueError(f"Undeclared positive intersection: {first}/{second}: {volume}")
        row = allowed
        direction = App.Vector(*row["axis"])
        start = App.Vector(*row["seat_point_mm"]) + direction*(row["frame_grip_mm"]-1e-6)
        mask = Part.makeCylinder(row["thread_major_radius_mm"]+1e-6, row["engagement_mm"]+2e-6, start, direction)
        outside = abs(common.cut(mask).Volume)
        maximum = math.pi*(row["thread_major_radius_mm"]**2-row["thread_minor_radius_mm"]**2)*row["engagement_mm"]
        if outside > 1e-6 or volume > maximum+1e-5:
            raise ValueError("Intersection exceeds the declared local thread representation")
        positive.append({"a": first, "b": second, "volume_mm3": volume, "type": "bounded_major_minor_thread",
                         "outside_thread_mask_mm3": outside, "upper_volume_mm3": maximum})
    thread_presence = verify_thread_presence(shapes, joints)
    contacts, contact_cache = [], {}
    for row in joints:
        stack = row.get("stack", [row["clamped_part"], row["receiver"]])
        pairs = [(first, second, "declared clamped stack bearing") for first, second in zip(stack, stack[1:])]
        pairs.append((row["fastener"], row["clamped_part"], "declared fastener head seat"))
        for first, second, role in pairs:
            key = frozenset((first, second))
            if key not in contact_cache:
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
                contact_cache[key] = distance, contact_area
            distance, contact_area = contact_cache[key]
            if distance > 1e-6 or contact_area <= 1:
                raise ValueError(f"A required physical bearing/seat contact is absent: {first}/{second}")
            contacts.append({"a": first, "b": second, "role": role, "distance_mm": distance,
                             "common_surface_area_mm2": contact_area})
    return {"undeclared_positive_intersections": 0, "bounded_threads": positive,
            "declared_thread_presence": thread_presence, "intentional_contacts": contacts}


def verify_cap_path(shapes):
    fixed = ["E_CORNER_PPP"] + ["E_FRAME_BOARD_"+axis for axis in "XYZ"] + ["E_FRAME_SCREW_PPP_"+axis for axis in "XYZ"]
    samples = []
    for offset in (0, .1, .25, .5, .75, 1, 1.5, 2, 4, 8):
        cap = shapes["E_CORNER_CAP_PPP"].copy()
        cap.translate(App.Vector(offset, offset, offset))
        volumes = {name: abs(cap.common(shapes[name]).Volume) for name in fixed}
        distances = {name: cap.distToShape(shapes[name])[0] for name in fixed}
        if max(volumes.values()) > 1e-6 or (offset > 0 and min(distances.values()) <= 1e-6):
            raise ValueError("The nominal local cap installation path is obstructed")
        samples.append({"translation_mm": [offset]*3, "max_positive_volume_mm3": max(volumes.values()),
                        "minimum_distance_mm": min(distances.values())})
    closed = corner_cap_positive(open_access=False)
    closed.translate(App.Vector(.5, .5, .5))
    red_volume = closed.common(corner_positive()).Volume
    if red_volume <= 1e-6:
        raise ValueError("The closed-hole installation negative fixture did not reproduce obstruction")
    return {"direction": "Translate along the body diagonal, with unchanged orientation; remove cap retaining screw first.",
            "opening": "Three open-ended capsule slots, not three closed orthogonal holes",
            "samples": samples, "closed_hole_negative_at_half_mm_volume_mm3": red_volume,
            "scope": "Local nominal rigid cap path only; not full assembly access or physical tolerances approval"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope", choices=("corner", "cage", "holders"), default="corner")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new private slice output directory")
    shapes, joints = corner_slice() if args.scope == "corner" else frame_cage()
    if args.scope == "holders":
        from enclosure_holders import holders
        extra, extra_joints, holder_details = holders()
        shapes.update(extra)
        joints.extend(extra_joints)
    validate_joints(shapes, joints)
    lengths = verify_fastener_lengths(shapes, joints)
    holder_checks = verify_holder_conditions(shapes, joints, holder_details) if args.scope == "holders" else None
    expected = {}
    for name, shape in shapes.items():
        assert_shape(shape, name)
        if len(shape.Solids) != 1:
            raise ValueError("An enclosure part must be one connected solid: " + name)
        box = (bounds(shape) if name.startswith(("E_HOLDER_", "E_REF_BOARD_", "E_SPACER_", "E_WASHER_", "E_BOARD_SCREW_"))
               else analytical_bounds(name))
        if max(abs(a-b) for a,b in zip(bounds(shape),box)) > 1e-6:
            raise ValueError("Primitive shape departed from its independent dimension contract")
        expected[name] = {"bbox_mm": box, "center_of_mass_mm": shape_centroid(shape),
                          "volume_mm3": shape.Volume, "solid_count": len(shape.Solids),
                          "is_reference": name.startswith("E_REF_BOARD_")}
    collision = verify_collisions(shapes, joints)
    outer = verify_outer_surfaces(shapes) if args.scope != "corner" else None
    cap_path = verify_cap_path(shapes) if args.scope == "cage" else None
    try:
        validate_joints(shapes, [dict(joints[0], receiver="MISSING_RECEIVER")])
    except ValueError:
        missing_rejected = True
    else:
        raise ValueError("Missing-mate negative control passed")
    test_joint = next(row for row in joints if not row["id"].startswith("EC_CAP_"))
    direction = App.Vector(*test_joint["axis"])
    start = App.Vector(*test_joint["seat_point_mm"]) + direction*(test_joint["frame_grip_mm"]-.01)
    oversized = dict(shapes)
    oversized[test_joint["receiver"]] = shapes[test_joint["receiver"]].cut(
        Part.makeCylinder(test_joint["thread_major_radius_mm"]+.1, test_joint["tap_depth_mm"]+.02, start, direction))
    oversize_volume = abs(oversized[test_joint["fastener"]].common(oversized[test_joint["receiver"]]).Volume)
    try:
        verify_collisions(oversized, joints)
    except ValueError as error:
        if "Nominal thread representation missing" not in str(error):
            raise
        oversize_rejected = True
    else:
        raise ValueError("An oversized receiver with no thread engagement passed")
    args.output.mkdir(parents=True)
    stem = {"corner": "corner-slice", "cage": "frame-cage", "holders": "enclosure-holders"}[args.scope]
    native, step = args.output/(stem+".FCStd"), args.output/(stem+".step")
    with tempfile.TemporaryDirectory(prefix="independent-corner-") as directory:
        raw = Path(directory)
        doc = App.newDocument("IndependentEnclosureSlice")
        doc.CreatedBy = ""
        doc.Comment = "Independent nominal enclosure slice; reference boards are unqualified. Not fabrication approval."
        objects = []
        for name, shape in shapes.items():
            obj = doc.addObject("Part::Feature", name)
            obj.Label = name
            obj.Shape = shape.copy()
            obj.addProperty("App::PropertyBool", "IsReference"); obj.IsReference = expected[name]["is_reference"]
            obj.addProperty("App::PropertyBool", "PhysicalQualified"); obj.PhysicalQualified = False
            obj.addProperty("App::PropertyString", "GeometryOrigin"); obj.GeometryOrigin = "new-independent-primitives"
            objects.append(obj)
        doc.recompute()
        doc.saveAs(str(raw/"slice.FCStd")); Import.export(objects, str(raw/"slice.step"))
        App.closeDocument(doc.Name)
        normalized_native(raw/"slice.FCStd", native); normalized_step(raw/"slice.step", step)
    saved = readback(native, step, expected)
    saved["expected_pose_basis"] = "Analytical cage bounds and pre-document holder shapes/centroids, never saved-object-derived expectations"
    before = digest(native)
    doc = App.openDocument(str(native))
    try:
        obj = doc.getObject("E_COUPON_X" if args.scope == "corner" else "E_FRAME_MOTOR_X")
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
    report = {"status": "PASS", "scope": args.scope, "cad_slice_complete": True, "full_enclosure_complete": False,
              "parts": expected, "joints": joints, "geometry": collision, "readback": saved,
              "fastener_lengths": lengths, "holder_conditions": holder_checks,
              "outer_surface_coverage": outer,
              "cap_local_installation": cap_path,
              "negative_controls": {"missing_mate_rejected": missing_rejected, "wrong_pose_rejected": pose_rejected},
              "source_geometry_read": False, "whole_fit": False, "build_ready": False, "physical_ready": False}
    report["negative_controls"].update({"oversized_receiver_rejected": oversize_rejected,
                                        "oversized_receiver_common_mm3": oversize_volume})
    report["generator_sha256"] = {name:digest(Path(__file__).parent/name) for name in
                                 ("check_corner_slice.py","enclosure_geometry.py","enclosure_holders.py",
                                  "build_cad.py","geometry_contract.py")}
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":"PASS","parts":len(shapes),"joints":len(joints),
                      "bounded_threads":len(collision["bounded_threads"]),
                      "intentional_contacts":len(collision["intentional_contacts"]),
                      "native_sha256":digest(native),"step_sha256":digest(step)},indent=2))


if __name__ == "__main__":
    main()
