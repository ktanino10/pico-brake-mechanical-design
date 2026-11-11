"""Build a self-contained nominal enclosure candidate from new and frozen public shapes."""
from pathlib import Path
import argparse
import csv
import json
import math
import tempfile

import FreeCAD as App
import Import
import Part

from build_cad import (assert_shape, bounds, digest, mesh_payload, normalized_native,
                       normalized_step, readback, shape_centroid)
from check_corner_slice import (analytical_bounds, validate_joints, verify_collisions,
                                verify_fastener_lengths, verify_holder_conditions,
                                verify_outer_surfaces, verify_thread_presence)
from enclosure_assembly import integrated_assembly
from enclosure_coverage import source_coverage
from enclosure_policy import (CAGE_IDS, ENCLOSURE_IDS, HOLDER_IDS, PUBLIC_CATALOG_SHA256,
                              validate_enclosure_ids, validate_public_brake_identity)
from geometry_contract import axis_point, require_pose
from public_policy import SOURCE_SHA256
from public_scan import inspect_file

ROOT = Path(__file__).resolve().parents[1]
FLAGS = {"whole_fit":False,"build_ready":False,"physical_ready":False}


def write_json(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(",",":"))+"\n")


def explode_offset(part):
    name = part["id"]
    if not name.startswith("E_"):
        return axis_point([0,0,part["explode_mm"][2]-35],name[0])
    if name.startswith(("E_REF_MOTOR_", "E_REF_SHAFT_")):
        return axis_point([0,0,65],name[-1])
    if name.startswith(("E_FRAME_MOTOR_", "E_FRAME_BOARD_", "E_HOLDER_FIX_")):
        offset = [0,0,0]
        offset["XYZ".index(name[-1])] = -85 if "MOTOR" in name else 85
        return offset
    if name.startswith(("E_CORNER_", "E_CAP_SCREW_", "E_FRAME_SCREW_")):
        octant = name.split("_")[-2] if name.startswith("E_FRAME_SCREW_") else name[-3:]
        distance = 55 if name.startswith(("E_CORNER_CAP_", "E_CAP_SCREW_")) else 30
        offset = [(1 if letter == "P" else -1)*distance for letter in octant]
        if "SCREW" in name:
            offset = [value*1.35 for value in offset]
        return offset
    distance = 110 if "MPU" in name else 55
    distance += ({"E_REF_BOARD_":20,"E_SPACER_":10,"E_WASHER_":30,"E_BOARD_SCREW_":45}
                 .get(next((prefix for prefix in ("E_REF_BOARD_","E_SPACER_","E_WASHER_","E_BOARD_SCREW_")
                            if name.startswith(prefix)),""),0))
    return [distance/math.sqrt(3)]*3


def negative_controls(shapes, joints, expected):
    first = joints[0]
    try:
        validate_joints(shapes,[dict(first,receiver="ABSENT_RECEIVER")])
    except ValueError:
        pass
    else:
        raise ValueError("Missing-receiver negative was accepted")
    moved = shapes["E_HOLDER_PCB"].copy()
    moved.translate(App.Vector(.25,0,0))
    try:
        require_pose(bounds(moved),shape_centroid(moved),expected["E_HOLDER_PCB"],"E_HOLDER_PCB")
    except ValueError:
        pass
    else:
        raise ValueError("Wrong-holder-pose negative was accepted")
    for roster in ([*ENCLOSURE_IDS,"SRC_ORIGINAL_PICO_FRAME"],list(ENCLOSURE_IDS)[1:]):
        try:
            validate_enclosure_ids(roster)
        except ValueError:
            pass
        else:
            raise ValueError("Original/missing part roster negative was accepted")
    try:
        validate_public_brake_identity(SOURCE_SHA256,PUBLIC_CATALOG_SHA256)
    except ValueError:
        pass
    else:
        raise ValueError("Protected full-C08 input identity was accepted")
    row = next(item for item in joints if item["fastener"] == "Z_MOTOR_INTERFACE_BOLT_0")
    enlarged = dict(shapes)
    start = App.Vector(*row["seat_point_mm"])+App.Vector(*row["axis"])*(row["frame_grip_mm"]-.001)
    enlarged[row["receiver"]] = shapes[row["receiver"]].cut(
        Part.makeCylinder(1.6,row["tap_depth_mm"]+.002,start,App.Vector(*row["axis"])))
    common = abs(enlarged[row["receiver"]].common(shapes[row["fastener"]]).Volume)
    try:
        verify_thread_presence(enlarged,[row])
    except ValueError:
        pass
    else:
        raise ValueError("Oversized nominal motor receiver was accepted")
    return {"missing_receiver_rejected":True,"wrong_holder_pose_rejected":True,
            "original_or_missing_geometry_roster_rejected":True,"full_private_c08_identity_rejected_before_import":True,
            "oversized_motor_receiver_rejected":True,"oversized_motor_receiver_common_mm3":common}


def cap_scope_extension(shapes):
    normal = App.Vector(1,1,1); normal.normalize()
    rotation = App.Rotation(normal,App.Vector(0,0,1))

    def projected_bounds(shape):
        copy = shape.copy()
        copy.transformShape(App.Placement(App.Vector(),rotation).toMatrix())
        box = bounds(copy)
        return box[2],box[5]

    cap_minimum = projected_bounds(shapes["E_CORNER_CAP_PPP"])[0]
    added_maximum, owner = -math.inf,None
    for name in set(shapes)-set(CAGE_IDS):
        maximum = projected_bounds(shapes[name])[1]
        if maximum > added_maximum:
            added_maximum,owner = maximum,name
    if added_maximum >= cap_minimum:
        raise ValueError("Added geometry requires a new cap approach-path assessment")
    return {"existing_local_cap_path":"Accepted open-slot path from cage slice-04, unchanged cap/frame geometry",
            "node_change":"Only subtractive inner relief; cannot introduce a new cap collision",
            "new_part_separation_proof":"All added parts lie below the cap's minimum body-diagonal plane; outward translation increases separation",
            "cap_minimum_projection_mm":cap_minimum,"added_maximum_projection_mm":added_maximum,
            "limiting_added_part":owner,"separation_mm":cap_minimum-added_maximum,
            "scope":"Nominal local cap approach only, not a complete assembly/tool-access qualification"}


def save_cad(shapes, parts, folder):
    native,step = folder/"downloads/enclosure-nominal.FCStd",folder/"downloads/enclosure-nominal.step"
    with tempfile.TemporaryDirectory(prefix="independent-enclosure-") as directory:
        temporary = Path(directory)
        doc = App.newDocument("IndependentEnclosure")
        doc.Label = "138 mm nominal enclosure / unqualified motor interface"
        doc.Comment = "Independent editable shape/placement snapshot. No original Pico shapes or external links. Not fabrication-ready."
        doc.CreatedBy = ""
        objects = []
        for part in parts:
            obj = doc.addObject("Part::Feature",part["id"])
            obj.Label = part["id"]
            obj.Shape = shapes[part["id"]].copy()
            for key,value in {"PublicPartId":part["id"],"JapaneseName":part["label"],
                              "Provenance":part["provenance"],"Role":part["role"]}.items():
                obj.addProperty("App::PropertyString",key)
                setattr(obj,key,value)
            for key,value in {"IsReference":part["is_reference"],"PhysicalQualified":False}.items():
                obj.addProperty("App::PropertyBool",key)
                setattr(obj,key,value)
            objects.append(obj)
        doc.recompute()
        doc.saveAs(str(temporary/"enclosure.FCStd"))
        Import.export(objects,str(temporary/"enclosure.step"))
        App.closeDocument(doc.Name)
        normalized_native(temporary/"enclosure.FCStd",native)
        normalized_step(temporary/"enclosure.step",step)
    return native,step


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new candidate output directory; do not overwrite an existing receipt")
    shapes,parts,joints,expected,holders = integrated_assembly()
    for name,shape in shapes.items():
        assert_shape(shape,name)
        if len(shape.Solids) != 1:
            raise ValueError("Each modeled instance must be one connected solid: "+name)
        require_pose(bounds(shape),shape_centroid(shape),expected[name],name)
        if name in CAGE_IDS and max(abs(a-b) for a,b in zip(bounds(shape),analytical_bounds(name))) > 1e-6:
            raise ValueError("Independent cage dimension contract changed")
    validate_joints(shapes,joints)
    lengths = verify_fastener_lengths(shapes,joints)
    controls = negative_controls(shapes,joints,expected)
    holder_shapes = {name:shapes[name] for name in (*CAGE_IDS,*HOLDER_IDS)}
    holder_joints = [row for row in joints if row["fastener"] in holder_shapes]
    holder_controls = verify_holder_conditions(holder_shapes,holder_joints,holders)
    print(f"Checking {len(shapes)} solids / {len(joints)} complete nominal fastener chains",flush=True)
    collision = verify_collisions(shapes,joints)
    outer = verify_outer_surfaces(shapes)
    cap_extension = cap_scope_extension(shapes)
    coverage = source_coverage(joints)
    print("BRep/coverage checks passed; writing fresh native, STEP and mesh",flush=True)
    for name in ("data","downloads","validation"):
        (args.output/name).mkdir(parents=True)
    native,step = save_cad(shapes,parts,args.output)
    saved = readback(native,step,expected)
    saved["expected_pose_basis"] = "Pre-document new primitives plus frozen public C08 exact bbox/centroid transformed by independent axis equations"
    payload,mesh_check = mesh_payload(shapes,parts)
    mesh_path = args.output/"data/enclosure-meshes.json"
    write_json(mesh_path,payload)
    for part in parts:
        part["explode_mm"] = explode_offset(part)
    conditions = json.loads((ROOT/"data/enclosure-nominal-conditions.json").read_text())
    manifest = {
        "schema":"independent-enclosure-assembly-v1","units":"mm","model_part_count":len(parts),
        "reference_part_count":sum(part["is_reference"] for part in parts),
        "fastener_count":len(joints),"parts":parts,"joints":joints,"nominal_conditions":conditions,
        "mesh":{"path":"data/enclosure-meshes.json","sha256":digest(mesh_path)},
        "source_leaf_count":83,"source_coverage_path":"data/enclosure-source-coverage.json",
        "old_reference_frames_in_integrated_model":0,"original_shapes_copied":0,
        "original_motor_overlap_mm3":29.606056754452105,"reference_motor_CAD_nominal_fit":"failed",
        "actual_hardware_compatibility":"unverified/blocked",
        "known_limits":json.loads((ROOT/"data/assembly.json").read_text())["known_limits"],
        "battery_harness_fit":"Unresolved; no battery geometry from the old 176 mm illustration is adopted",
        "nominal_enclosure_part_coverage_complete":True,**FLAGS,
    }
    write_json(args.output/"data/enclosure-assembly.json",manifest)
    write_json(args.output/"data/enclosure-source-coverage.json",coverage)
    with (args.output/"data/enclosure-parts.csv").open("w",newline="",encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id","label","model_instance_count","group","is_reference","provenance","mates","volume_mm3","bbox_mm","physical_qualified","procurement_quantity"])
        for part in parts:
            writer.writerow([part["id"],part["label"],1,part["group"],part["is_reference"],part["provenance"],
                             "|".join(part["mates"]),part["volume_mm3"],json.dumps(part["bbox_mm"]),False,"UNSPECIFIED"])
    with (args.output/"data/enclosure-joints.csv").open("w",newline="",encoding="utf-8-sig") as stream:
        fields = ["id","fastener","clamped_part","receiver","stack","axis","seat_point_mm","nominal_thread",
                  "nominal_length_mm","length_convention","modeled_total_length_mm","frame_grip_mm",
                  "engagement_mm","tap_depth_mm","receiver_end","bottom_margin_mm","protrusion_mm","tightening_torque_Nm","physical_ready"]
        writer = csv.DictWriter(stream,fieldnames=fields,extrasaction="ignore")
        writer.writeheader()
        for row in joints:
            values = dict(row,receiver_end=row.get("receiver_end","blind"),
                          stack=row.get("stack",[row["clamped_part"],row["receiver"]]))
            writer.writerow({key:json.dumps(value) if isinstance(value,list) else value for key,value in values.items()})
    provenance = {
        "schema":"independent-enclosure-provenance-v1","original_geometry_permission":"UNKNOWN / NOT REDISTRIBUTED",
        "new_parts":[{"id":part["id"],"origin":part["provenance"],"external_links":False} for part in parts],
        "source_roster_disposition":"enclosure-source-coverage.json","fixed_public_input":saved["expected_pose_basis"],
        "excluded_public_placeholders":["REF_FRAME","REF_MOTOR_ENVELOPE"],
        "shaft_reference":"Frozen independent public REF_SHAFT, relabelled required-interface reference, not source motor geometry",
        "no_original_STL_STEP_3MF_or_manufacturer_files_in_payload":True,**FLAGS,
    }
    write_json(args.output/"data/enclosure-provenance.json",provenance)
    report = {"status":"PASS","model_parts":len(parts),"fasteners":len(joints),"readback":saved,
              "geometry":collision,"fastener_lengths":lengths,"mesh":mesh_check,"negative_controls":controls,
              "holder_condition_controls":holder_controls,"outer_material_surfaces":outer,
              "cap_scope_extension":cap_extension,"source_leaf_dispositions":83,**FLAGS}
    report["input_sha256"] = {name:digest(ROOT/name) for name in ("downloads/brake-single.FCStd","data/assembly.json","data/enclosure-nominal-conditions.json")}
    report["generator_sha256"] = {name:digest(ROOT/"scripts"/name) for name in
                                 ("build_enclosure.py","enclosure_assembly.py","enclosure_geometry.py","enclosure_holders.py",
                                  "enclosure_policy.py","enclosure_coverage.py","check_corner_slice.py","build_cad.py","geometry_contract.py")}
    write_json(args.output/"validation/enclosure-cad.json",report)
    entries = []
    for path in sorted(args.output.rglob("*")):
        if path.is_file():
            relative = path.relative_to(args.output).as_posix()
            inspect_file(path,relative)
            entries.append({"path":relative,"sha256":digest(path),"bytes":path.stat().st_size})
    write_json(args.output/"data/enclosure-checksums.json",{"downloads_ready":True,"files":entries,**FLAGS})
    print(json.dumps({"status":"PASS","parts":len(parts),"joints":len(joints),
                      "native_sha256":digest(native),"step_sha256":digest(step),"mesh_sha256":digest(mesh_path)},indent=2))


if __name__ == "__main__":
    main()
