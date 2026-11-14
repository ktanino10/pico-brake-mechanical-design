"""Read public C08 only; export visual groups and explanatory cuts without saving CAD."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parent


def mesh(shape):
    vertices, faces = shape.tessellate(.16)
    return {"vertices": [[v.x, v.y, v.z] for v in vertices], "faces": [list(f) for f in faces]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args()
    repo = args.repo
    assembly = json.loads((repo / "data/assembly.json").read_text())
    provenance = {p["public_part"]: p for p in json.loads((repo / "data/provenance.json").read_text())["included"]}
    doc = App.openDocument(str((repo / "downloads/brake-single.FCStd").resolve()))
    items = []
    half = Part.makeBox(200, 100, 150, App.Vector(-100, -100, -100))
    slab = Part.makeBox(1.2, 8, 30, App.Vector(-.6, 32, -72))
    axial = []
    for p in assembly["parts"]:
        name = p["id"]
        if name == "ARMATURE" or name.startswith(("SPRING_CLAMP_TIP_", "SPRING_TIP_BOLT_", "SPRING_TIP_NUT_PLATE_")):
            role = "rotate_and_axial"
        elif name.startswith("SPRING_") and name[len("SPRING_"):].isdigit():
            role = "rotating_spring"
        elif p["group"] in ("coil", "support", "wiring") or name.startswith(
                ("FRAME_BOLT_", "STATOR_BOLT_", "CAP_BOLT_", "RETAINER_BOLT_", "STRAIN_BOLT_", "MOTOR_INTERFACE_BOLT_")):
            role = "fixed"
        elif name in ("REF_FRAME", "REF_MOTOR_ENVELOPE") or name.startswith("BEARING_BALL_"):
            role = "fixed_reference"
        else:
            role = "rotate_only"
        shape = doc.getObject("Z_" + name).Shape
        source_bbox = p["bbox_mm"]
        info = {"id": name, "label": p["label"], "material_code": p["material_code"],
                "motion_group": role, "is_reference": p["is_reference"],
                "source": provenance[name], "source_bbox_mm": source_bbox, **mesh(shape)}
        if role == "fixed":
            cut = shape.cut(half)
            if cut.Volume > 1e-7:
                info["cutaway"] = mesh(cut)
        if name in ("ARMATURE", "YOKE", "WINDING", "BOBBIN", "COIL_RETAINER", "POLE_CAP_INNER", "POLE_CAP_OUTER", "REF_WHEEL") or name.startswith("LINING_"):
            cut = shape.common(slab)
            if cut.Volume > 1e-7:
                axial.append({"id": name, "label": p["label"], "material_code": p["material_code"],
                              "motion_group": role, "is_reference": p["is_reference"], **mesh(cut)})
        if role == "rotating_spring":
            index = int(name.rsplit("_", 1)[1])
            angle = math.radians(index * 120)
            weights = []
            for x, y, z in info["vertices"]:
                local_y = -x * math.sin(angle) + y * math.cos(angle)
                u = min(1, max(0, (local_y - 6) / 24))
                weights.append(u * u * (3 - 2 * u))
            info["axial_weights"] = weights
        items.append(info)
    arm = doc.getObject("Z_ARMATURE").Shape
    linings = [doc.getObject("Z_LINING_" + str(i)).Shape for i in range(3)]
    contacts = []
    for delta in (0, .1, .199, .2, .201):
        moved = arm.copy()
        moved.translate(App.Vector(0, 0, delta))
        contacts.append({"delta_z_mm": delta, "gap_mm": [moved.distToShape(l)[0] for l in linings],
                         "intersection_mm3": [moved.common(l).Volume for l in linings]})
    assert all(abs(g - .2) < 1e-7 for g in contacts[0]["gap_mm"])
    assert all(g < 1e-7 for g in contacts[3]["gap_mm"])
    assert all(v < 1e-7 for v in contacts[3]["intersection_mm3"])
    assert all(v > 0 for v in contacts[4]["intersection_mm3"])
    App.closeDocument(doc.Name)

    enclosure = json.loads((repo / "data/enclosure-meshes.json").read_text())
    frames_mesh = []
    for p in enclosure["parts"]:
        if p["id"].startswith(("E_FRAME_MOTOR_", "E_FRAME_BOARD_", "E_CORNER_")):
            positions, indices = p["positions"], p["indices"]
            frames_mesh.append({"id": p["id"], "vertices": [positions[i:i+3] for i in range(0, len(positions), 3)],
                                "faces": [indices[i:i+3] for i in range(0, len(indices), 3)]})
    fps, duration = 24, 22
    frames = []
    rotor_angle = 0
    for i in range(fps * duration):
        t = i / fps
        if t < 4:
            stage, speed, travel = "three_axes", 0, 0
        elif t < 7:
            stage, speed, travel = "one_axis", 0, 0
        elif t < 10:
            stage, speed, travel = "rotate", 50, 0
        elif t < 12:
            stage, speed, travel = "coast", 50 - 5 * ((t - 10) / 2), 0
        elif t < 14:
            u = (t - 12) / 2
            stage, speed, travel = "attract", 45, .2 * u * u * (3 - 2 * u)
        elif t < 16:
            u = (t - 14) / 2
            stage, speed, travel = "brake", 45 * (1 - u * u * (3 - 2 * u)), .2
        elif t < 17.5:
            stage, speed, travel = "stopped", 0, .2
        elif t < 20:
            u = (t - 17.5) / 2.5
            stage, speed, travel = "release", 0, .2 * (1 - u * u * (3 - 2 * u))
        else:
            stage, speed, travel = "released", 0, 0
        rotor_angle += speed / fps
        frames.append({"frame": i+1, "t": t, "stage": stage, "angle_deg": rotor_angle,
                       "render_speed_deg_s": speed, "axial_mm": travel,
                       "motor_drive_on": 7 <= t < 10, "coil_on": 12 <= t < 17.5})
    sources = ["data/assembly.json", "data/meshes.json", "data/provenance.json", "data/enclosure-assembly.json",
               "data/enclosure-meshes.json", "docs/PUBLIC_SCOPE.md", "docs/ENCLOSURE.md", "downloads/brake-single.FCStd"]
    payload = {"schema": "public-c08-coaxial-explanation-v1", "fps": fps, "duration_s": duration,
               "parts": items, "axial_section": axial, "enclosure_frames": frames_mesh,
               "frames": frames, "axis_quaternions_xyzw": assembly["axis_quaternions_xyzw"],
               "contact_checks": contacts, "hub_axial_motion_mm": 0, "armature_max_axial_mm": .2,
               "physical_ready": False, "build_ready": False, "attitude_control_success_shown": False,
               "spring_deflection": "Smooth axial displacement root0 to tip0.2mm; illustrative, not FEA",
               "source_hashes": [{"path": n, "sha256": hashlib.sha256((repo/n).read_bytes()).hexdigest()} for n in sources]}
    (ROOT / "c08-scene-data.json").write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")
    group_map = {r: [p["id"] for p in items if p["motion_group"] == r] for r in
                 ("fixed", "fixed_reference", "rotate_only", "rotate_and_axial", "rotating_spring")}
    (ROOT / "c08-source-groups.json").write_text(json.dumps({"source_hashes": payload["source_hashes"],
         "motion_groups": group_map, "omitted_visual_details": ["BEARING_BALL_* internal bearing kinematics",
         "Full view uses new independent138mm frame references, not private Pico assembly"],
         "fixed_axial_hub": True, "contact_checks": contacts}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"parts": len(items), "groups": {k:len(v) for k,v in group_map.items()},
                      "frame_parts":len(frames_mesh),"section_parts":len(axial),"frames":len(frames),
                      "armature_travel_mm":.2,"hub_axial_motion_mm":0},indent=2))


if __name__ == "__main__":
    main()
