"""Combine new primitives and fixed public C08 shapes, without original Pico geometry."""
import json
import math
from pathlib import Path

import FreeCAD as App
import Part

from build_cad import AXIS_ROTATIONS, assert_shape, bounds, digest, shape_centroid
from enclosure_geometry import frame_cage
from enclosure_holders import holders
from enclosure_policy import validate_enclosure_ids, validate_public_brake_identity
from geometry_contract import axis_point, expected_instances, require_pose
from public_policy import ALLOWED, family

ROOT = Path(__file__).resolve().parents[1]

# z seat, direction, major/minor radii, grip, engagement, length, head height,
# receiver hole depth, end condition. These are geometry conditions, not torque approval.
THREADS = {
    "FRAME_BOLT": (-68, 1, 1.5, 1.25, 16.5, 2.4, 20, 0, 2.4, "through"),
    "STATOR_BOLT": (-41.3, -1, 1.5, 1.25, 5.5, 6.5, 12, 3, 8, "blind"),
    "WHEEL_BOLT": (-68, 1, 1.5, 1.25, 3.2, 2.4, 8, 0, 2.4, "through"),
    "SPRING_ROOT_BOLT": (-68, 1, 1, .8, 4, 1.6, 6, 0, 1.6, "through"),
    "SPRING_TIP_BOLT": (-61.55, -1, 1, .8, 3.65, 1.6, 6, 0, 1.6, "through"),
    "RETAINER_BOLT": (-60.8, 1, 1.25, 1.025, 1.8, 6.2, 8, 0, 8, "blind"),
    "CAP_BOLT": (-63.3, 1, 1, .8, 1.5, 4.5, 6, 0, 5.3, "blind"),
    "STRAIN_BOLT": (-41.8, -1, 1, .8, 2, 3, 5, 2, 3, "through"),
    "RELEASE_STOP": (-64.8, -1, 1, .8, 0, 2.8, 2.8, 1.2, 3, "blind"),
    "RIM_BOLT": (-68, 1, 2, 1.65, 3.2, 3.2, 8, 0, 3.2, "through"),
    "HUB_CONNECT_BOLT": (-68, 1, 1, .8, 1.5, 2.5, 4, 0, 2.9, "blind"),
    "MOTOR_INTERFACE_BOLT": (-58, 1, 1.5, 1.25, 3, 4, 7, 0, 4.5, "blind"),
}


def published_brake():
    native, catalog = ROOT/"downloads/brake-single.FCStd", ROOT/"data/assembly.json"
    validate_public_brake_identity(digest(native), digest(catalog))
    payload = json.loads(catalog.read_text())
    expected = expected_instances(payload["parts"], ("Z",))
    doc = App.openDocument(str(native))
    shapes = {}
    try:
        leaves = [obj for obj in doc.Objects if obj.TypeId == "Part::Feature"]
        if {obj.Name for obj in leaves} != set(expected):
            raise ValueError("Published native roster differs from its fixed catalog")
        for obj in leaves:
            row = expected[obj.Name]
            assert_shape(obj.Shape, obj.Name)
            require_pose(bounds(obj.Shape), shape_centroid(obj.Shape), row, obj.Name)
            if obj.OutList or abs(obj.Shape.Volume-row["volume_mm3"]) > 1e-5:
                raise ValueError("Published source shape dependency or volume mismatch")
            shapes[obj.Name.removeprefix("Z_")] = obj.Shape.copy()
    finally:
        App.closeDocument(doc.Name)
    validate_public_brake_identity(digest(native), digest(catalog))
    return shapes, payload


def nominal_motor_interface():
    body = Part.makeCylinder(18, 5.2, App.Vector(0, 0, -55))
    body = body.fuse(Part.makeCylinder(14, 22, App.Vector(0, 0, -55)))
    for angle in (180, 60, 300):
        x, y = 15*math.cos(math.radians(angle)), 15*math.sin(math.radians(angle))
        body = body.cut(Part.makeCylinder(1.25, 4.5001, App.Vector(x, y, -55.0001)))
    return body.removeSplitter()


def world_shape(shape, axis):
    result = shape.copy()
    result.transformShape(App.Placement(App.Vector(), AXIS_ROTATIONS[axis]).toMatrix())
    return result


def endpoint(name, axis):
    replacements = {"REF_FRAME":"E_FRAME_MOTOR_"+axis,
                    "REF_MOTOR_ENVELOPE":"E_REF_MOTOR_"+axis, "REF_SHAFT":"E_REF_SHAFT_"+axis}
    return replacements[name] if name in replacements else axis+"_"+name


def brake_joint(part, axis):
    base = family(part["id"])
    z, direction, major, minor, grip, engagement, length, head, depth, end = THREADS[base]
    box = part["bbox_mm"]
    seat = axis_point([(box[0]+box[3])/2, (box[1]+box[4])/2, z], axis)
    stack = list(part["mates"])
    if base == "RETAINER_BOLT":
        stack.remove("COIL_RETAINER")
    if base == "RELEASE_STOP":
        stack = ["REF_WHEEL"]
    stack = [endpoint(name, axis) for name in stack]
    return {
        "id": axis+"_"+part["id"]+"_JOINT", "fastener":axis+"_"+part["id"],
        "clamped_part":stack[0], "receiver":stack[-1], "stack":stack,
        "axis":axis_point([0, 0, direction], axis), "seat_point_mm":seat,
        "thread_major_radius_mm":major, "thread_minor_radius_mm":minor,
        "frame_grip_mm":grip, "engagement_mm":engagement, "tap_depth_mm":depth,
        "receiver_end":end, "bottom_margin_mm":depth-engagement if end == "blind" else None,
        "protrusion_mm":max(0, length-grip-engagement) if end == "through" else None,
        "nominal_length_mm":length, "length_convention":"under-head" if head else "including-head",
        "head_height_mm":head, "modeled_total_length_mm":length+head,
        "nominal_thread":{1:"M2",1.25:"M2.5",1.5:"M3",2:"M4"}[major],
        "seat_kind":"Existing authored C08 nominal seat; major/minor cylindrical thread representation",
        "published_c08_joint_family":part["joint_id"],
        "new_torque_qualification":False, "tightening_torque_Nm":None, "physical_ready":False,
        "reference_only_motor_interface":base == "MOTOR_INTERFACE_BOLT",
    }


def new_part_record(name):
    reference = name.startswith("E_REF_")
    if name.startswith(("E_CAP_SCREW_", "E_FRAME_SCREW_", "E_HOLDER_FIX_", "E_BOARD_SCREW_", "E_WASHER_")):
        group, label = "fasteners", "筐体・保持部の締結部品"
    elif name.startswith("E_SPACER_"):
        group, label = "electronics", "名目絶縁スペーサー"
    elif name.startswith("E_HOLDER_"):
        group, label = "electronics", "独立設計の基板保持部"
    elif name.startswith("E_REF_BOARD_"):
        group, label = "reference", "基板の機械的参照（厚さ・部品高さは未確認）"
    elif reference:
        group, label = "reference", "要求モーターインターフェース参考（元motor適合は未解決）"
    elif name.startswith("E_CORNER_CAP_"):
        group, label = "enclosure", "外側コーナーカバー"
    elif name.startswith("E_CORNER_"):
        group, label = "enclosure", "内部三面接合ノード"
    else:
        group, label = "enclosure", "独立設計の支持フレーム"
    return {"id":name,"label":label,"group":group,"role":label,"is_reference":reference,
            "provenance":"independent-interface-reference" if reference else "new-independent-primitives",
            "material":"名目材質のみ・材証と実機適合は未資格","mates":[]}


def integrated_assembly():
    shapes, joints = frame_cage()
    extra, extra_joints, holder_details = holders()
    shapes.update(extra)
    joints.extend(extra_joints)
    parts = {name:new_part_record(name) for name in shapes}
    expected = {name:{"bbox_mm":bounds(shape),"center_of_mass_mm":shape_centroid(shape),
                     "volume_mm3":shape.Volume,"solid_count":len(shape.Solids),
                     "is_reference":parts[name]["is_reference"]} for name,shape in shapes.items()}
    canonical, catalog = published_brake()
    old_parts = [part for part in catalog["parts"] if part["id"] in (*ALLOWED, "REF_WHEEL")]
    expected.update(expected_instances(old_parts, "XYZ"))
    motor = nominal_motor_interface()
    for axis in "XYZ":
        for part in old_parts:
            name = axis+"_"+part["id"]
            shapes[name] = world_shape(canonical[part["id"]], axis)
            parts[name] = dict(part, id=name, label=axis+" / "+part["label"],
                               mates=[endpoint(mate, axis) for mate in part["mates"]],
                               provenance="fixed-public-input/"+part["provenance"])
            if part["is_fastener"]:
                joints.append(brake_joint(part, axis))
        for kind, shape in (("MOTOR", motor), ("SHAFT", canonical["REF_SHAFT"])):
            name = f"E_REF_{kind}_{axis}"
            shapes[name] = world_shape(shape, axis)
            parts[name] = new_part_record(name)
            parts[name]["reference_motor_CAD_nominal_fit"] = "failed"
            parts[name]["actual_hardware_compatibility"] = "unverified/blocked"
            expected[name] = {"bbox_mm":bounds(shapes[name]),"center_of_mass_mm":shape_centroid(shapes[name]),
                              "volume_mm3":shapes[name].Volume,"solid_count":1,"is_reference":True}
    validate_enclosure_ids(shapes)
    fasteners = {row["fastener"] for row in joints}
    for part in parts.values():
        part["is_fastener"] = part["id"] in fasteners
        part["joint_ids"] = [row["id"] for row in joints if part["id"] == row["fastener"] or
                             part["id"] in row.get("stack", [row["clamped_part"], row["receiver"]])]
        for row in joints:
            stack = [row["fastener"], *row.get("stack", [row["clamped_part"], row["receiver"]])]
            if part["id"] in stack:
                part["mates"].extend(name for name in stack if name != part["id"])
        part["mates"] = list(dict.fromkeys(part["mates"]))
        if any(mate not in shapes or mate == part["id"] for mate in part["mates"]):
            raise ValueError("Unknown integrated part counterpart: "+part["id"])
    return shapes, list(parts.values()), joints, expected, holder_details
