"""Original R1 bench-brake geometry. Nominal fit checks are not hardware approval."""
from pathlib import Path
import argparse
import csv
import hashlib
from html import escape
import json
import math
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET

import FreeCAD as App
import Import
import Mesh
import MeshPart
import Part

from geometry_contract import mesh_moments, require_pose

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "prototype/mechanical"
V = App.Vector
P = {
    "revision": "R1",
    "shaft_diameter_mm": 6.0,
    "shaft_length_mm": 100.0,
    "axis_height_mm": 72.0,
    "bearing_centers_x_mm": [24.0, 88.0],
    "bearing_size_mm": [6.0, 19.0, 6.0],
    "printed_bearing_bore_mm": 19.05,
    "rotor_center_x_mm": 50.0,
    "rotor_od_mm": 60.0,
    "rotor_id_mm": 12.10,
    "rotor_thickness_mm": 1.0,
    "rotor_pcd_mm": 19.0,
    "rotor_hole_mm": 3.2,
    "rotor_holes": 6,
    "pad_size_mm": [1.0, 10.0, 8.0],
    "pad_radius_mm": 24.0,
    "pad_center_gap_mm": 0.15,
    "lever_pivot_xy_mm": [50.0, 44.0],
    "lever_output_arm_mm": 20.0,
    "lever_input_arm_mm": 40.0,
    "solenoid_open_stroke_mm": 1.5,
    "solenoid_min_stroke_mm": 0.3,
    "max_lever_angle_deg": 0.8,
    "return_spring": {"model": "SAMINI 12-0423", "od_mm": 4.0,
                      "wire_mm": 0.3, "free_mm": 20.0, "rate_N_mm": 0.13,
                      "installed_open_mm": 16.5, "moment_arm_mm": 20.0},
    "coupling": {"model": "NBK MSTS-25C-6-6", "od_mm": 25.0,
                 "length_mm": 31.0, "engagement_each_mm": 8.5},
    "reported_motor_shaft_mm": {"A": 6.0, "B": 15.0, "C": 4.0, "D": 5.0},
    "motor_envelope_only": {"diameter_mm": 55.0, "length_mm": 65.0},
    "motor_saddle_body_range_mm": [40.0, 65.0],
    "sensor": {"model": "Cytron MAKER-REFLECT", "board_mm": [18.1, 8.4, 4.2],
               "header_projection_mm": 5.6, "gap_mm": 2.0,
               "gap_adjustment_mm": [1.0, 5.0], "cycles_per_rev": 12,
               "track_radius_mm": [13.5, 18.5], "sample_rate_Hz": 2000},
    "design_targets": {"initial_rpm": 150, "ceiling_rpm": 300, "stop_s": 1.0,
                       "max_energized_s": 1.0, "minimum_interval_s": 30,
                       "first_batch_stops": 5, "assembly_energy_budget_J": 0.1,
                       "pad_PLA_limit_C": 40, "solenoid_case_limit_C": 45,
                       "rotor_axial_TIR_mm": 0.10, "rotor_radial_TIR_mm": 0.15,
                       "shaft_endplay_mm": [0.10, 0.20],
                       "alignment_offset_mm": 0.03, "alignment_angle_deg": 0.3,
                       "minimum_solenoid_force_N": 1.5,
                       "minimum_pad_normal_each_N": 1.5,
                       "assumed_dynamic_mu": 0.2},
}


def box(x, y, z, dx, dy, dz):
    return Part.makeBox(dx, dy, dz, V(x, y, z))


def cyl(radius, length, origin, direction=(0, 0, 1)):
    return Part.makeCylinder(radius, length, V(*origin), V(*direction))


def annulus(outer, inner, length, origin, direction=(0, 0, 1)):
    return cyl(outer, length, origin, direction).cut(cyl(inner, length, origin, direction))


def bounds(shape):
    b = shape.optimalBoundingBox(False, False)
    return [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax]


def clean(shape):
    shape = shape.removeSplitter()
    if not shape.isValid() or len(shape.Solids) != 1 or shape.Volume <= 0:
        raise ValueError("Invalid or disconnected manufactured part")
    return shape.Solids[0]


def fuse(shapes):
    result = shapes[0]
    for shape in shapes[1:]:
        result = result.fuse(shape)
    return clean(result)


def xy_plate(points, z, thickness):
    wire = Part.makePolygon([V(x, y, z) for x, y in [*points, points[0]]])
    return Part.Face(wire).extrude(V(0, 0, thickness))


def bar(first, second, width, z, thickness):
    dx, dy = second[0] - first[0], second[1] - first[1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length * width / 2, dx / length * width / 2
    return fuse([xy_plate([(first[0] + nx, first[1] + ny), (second[0] + nx, second[1] + ny),
                           (second[0] - nx, second[1] - ny), (first[0] - nx, first[1] - ny)], z, thickness),
                 cyl(width / 2, thickness, (*first, z)),
                 cyl(width / 2, thickness, (*second, z))])


def slot(x, y, z, length, width, height):
    r = width / 2
    return fuse([box(x - length / 2, y - r, z, length, width, height),
                 cyl(r, height, (x - length / 2, y, z)),
                 cyl(r, height, (x + length / 2, y, z))])


def moved(shape, offset):
    result = shape.copy()
    result.translate(V(*offset))
    return result


def pivoted(shape, angle):
    result = shape.copy()
    result.rotate(V(50, 44, 72), V(0, 0, 1), angle)
    return result


def point_rotated(x, y, angle):
    a = math.radians(angle)
    x, y = x - 50, y - 44
    return (50 + x * math.cos(a) - y * math.sin(a),
            44 + x * math.sin(a) + y * math.cos(a))


def linkage(angle, right_angle=None):
    right_angle = angle if right_angle is None else right_angle
    front = point_rotated(45, 84, angle)
    pin = point_rotated(28, 84, -right_angle)
    a = math.radians(angle)
    u = (math.cos(a), math.sin(a))
    d = (front[0] - pin[0], front[1] - pin[1])
    along = d[0] * u[0] + d[1] * u[1]
    across = -d[0] * u[1] + d[1] * u[0]
    if abs(across) >= 10:
        raise ValueError("Solenoid link cannot reach")
    q = -along + math.sqrt(10**2 - across**2)
    return {"stroke_mm": -5.5 - q,
            "clevis_xy": [front[0] + q * u[0], front[1] + q * u[1]],
            "link_angle_deg": math.degrees(math.asin(across / 10)),
            "world_link_angle_deg": angle + math.degrees(math.asin(across / 10)),
            "link_pivot_xy": list(pin)}


def posed_parts(parts, angle, right_angle=None):
    right_angle = angle if right_angle is None else right_angle
    state = linkage(angle, right_angle)
    spring_a = point_rotated(41.75, 64, -right_angle)
    spring_b = point_rotated(58.25, 64, angle)
    spring_delta = V(spring_b[0] - spring_a[0], spring_b[1] - spring_a[1], 0)
    spring_length = spring_delta.Length
    spring_axis = spring_delta / spring_length
    spring_angle = math.degrees(math.atan2(spring_axis.y, spring_axis.x))
    result = []
    for part in parts:
        name = part["id"]
        shape = part["shape"]
        if part["group"] in ("jaw_L", "jaw_R"):
            shape = pivoted(shape, angle if part["group"] == "jaw_L" else -right_angle)
        elif name == "SOLENOID_LINK":
            shape = shape.copy()
            shape.rotate(V(28, 84, 86.3), V(0, 0, 1), state["world_link_angle_deg"])
            shape.translate(V(state["link_pivot_xy"][0] - 28, state["link_pivot_xy"][1] - 84, 0))
        elif name.startswith("LINK_PIN_"):
            x = 28 if name.endswith("1") else 38
            point = state["link_pivot_xy"] if name.endswith("1") else state["clevis_xy"]
            shape = moved(shape, (point[0] - x, point[1] - 84, 0))
        elif name == "PLUNGER_REFERENCE":
            shape = pivoted(shape, angle)
            a = math.radians(angle)
            travel = 1.5 - state["stroke_mm"]
            shape = moved(shape, (travel * math.cos(a), travel * math.sin(a), 0))
        elif name == "RETURN_SPRING_ENVELOPE":
            # End coils seat against tilting jaws; shorten the envelope to the nearest seat edges.
            margin_a = 2 * abs(math.sin(math.radians(-right_angle - spring_angle)))
            margin_b = 2 * abs(math.sin(math.radians(angle - spring_angle)))
            if angle or right_angle:
                margin_a += 1e-4
                margin_b += 1e-4
            start = V(*spring_a, 72) + margin_a * spring_axis
            shape = annulus(2, 1.7, spring_length - margin_a - margin_b, tuple(start), tuple(spring_axis))
        elif name == "SPRING_GUIDE":
            shape = shape.copy()
            shape.rotate(V(50, 64, 72), V(0, 0, 1), spring_angle)
            shape.translate(V((spring_a[0] + spring_b[0]) / 2 - 50,
                              (spring_a[1] + spring_b[1]) / 2 - 64, 0))
        result.append({**part, "shape": shape})
    return result


def drill_z(shape, points, radius=1.6):
    b = bounds(shape)
    for x, y in points:
        shape = shape.cut(cyl(radius, b[5] - b[2] + 2, (x, y, b[2] - 1)))
    return clean(shape)


def build():
    parts = []

    def add(name, shape, process, description, group="fixed", **extra):
        shape = clean(shape)
        parts.append({"id": name, "shape": shape, "process": process,
                      "description": description, "group": group, **extra})
        return shape

    base = box(-150, -60, 0, 290, 180, 12)
    base_holes = [(x, y) for x in (24, 88) for y in (-20, 20)]
    base_holes += [(x, y) for x in (25, 75) for y in (34, 67)]
    base_holes += [(x, y) for x in (-119, -39) for y in (-38, 38)]
    base_holes += [(69, -44), (69, -30)]
    base_holes += [(x, y) for x in (-130, 115) for y in (-40, 100)]
    base = drill_z(base, base_holes, 1.7)
    for x, y in [*((x, y) for x in (24, 88) for y in (-20, 20)),
                 *((x, y) for x in (25, 75) for y in (34, 67)), (69, -44), (69, -30)]:
        base = base.cut(cyl(4, 4, (x, y, 0)))
    add("BASE", base, "cut-drill", "Birch plywood 290 x 180 x 12; coordinates in base-drill.svg")

    shaft = cyl(3, 100, (0, 0, 72), (1, 0, 0))
    add("SHAFT", shaft, "order-machine", "SUS303 ground diameter6 g6 x100 +/-0.1; ends C0.2", "rotating")
    for i, x in enumerate(P["bearing_centers_x_mm"], 1):
        body = fuse([box(x - 5, -15, 12, 10, 30, 74),
                     box(x - 14, -25, 12, 28, 50, 6)])
        body = body.cut(cyl(P["printed_bearing_bore_mm"] / 2, 12, (x - 6, 0, 72), (1, 0, 0)))
        for y in (-12, 12):
            for z in (60, 84):
                body = body.cut(cyl(1.6, 12, (x - 6, y, z), (1, 0, 0)))
        body = drill_z(body, [(x, -20), (x, 20)])
        add(f"BEARING_BLOCK_{i}", body, "PLA", "626ZZ support, print upright with bore support; finish slip fit")
        add(f"BEARING_{i}", annulus(9.5, 3, 6, (x - 3, 0, 72), (1, 0, 0)),
            "buy", "626ZZ 6 x19 x6; simplified envelope, not a bearing manufacturing model")
        for side in (-1, 1):
            plate_x = x - 8 if side == -1 else x + 5
            cap = box(plate_x, -16, 56, 3, 32, 32)
            boss_x = x - 5 if side == -1 else x + 3.1
            cap = cap.fuse(annulus(9.45, 8.7, 1.9, (boss_x, 0, 72), (1, 0, 0)))
            cap = cap.cut(cyl(7, 5, (plate_x - 1, 0, 72), (1, 0, 0)))
            for y in (-12, 12):
                for z in (60, 84):
                    cap = cap.cut(cyl(1.6, 6, (plate_x - 1, y, z), (1, 0, 0)))
            add(f"BEARING_CAP_{i}_{'L' if side == -1 else 'R'}", cap, "PLA",
                "Outer-race retention lip only; 0.1mm axial clearance to bearing")
    for name, x in (("L", 15.6), ("R", 91.4)):
        add("SHAFT_COLLAR_" + name, annulus(6, 3, 5, (x, 0, 72), (1, 0, 0)),
            "buy", "IWATA SC0605S, M3 setscrew; envelope only", "rotating")
    for name, x in (("L", 20.7), ("R", 91.0)):
        add("THRUST_SHIM_" + name, annulus(4.25, 3.05, 0.3, (x, 0, 72), (1, 0, 0)),
            "order-machine", "SUS304 shim ID6.1 OD8.5 t0.3; inner-ring contact only", "rotating")

    hub = fuse([cyl(12.7, 5, (44.5, 0, 72), (1, 0, 0)),
                cyl(6, 4.2, (49.5, 0, 72), (1, 0, 0))])
    hub = hub.cut(cyl(3, 10, (44, 0, 72), (1, 0, 0)))
    rotor = annulus(30, P["rotor_id_mm"] / 2, 1, (49.5, 0, 72), (1, 0, 0))
    holes = []
    for n in range(6):
        a = math.radians(60 * n)
        y, z = 9.5 * math.cos(a), 72 + 9.5 * math.sin(a)
        holes.append((y, z - 72))
        rotor = rotor.cut(cyl(1.6, 2, (49, y, z), (1, 0, 0)))
        hub = hub.cut(cyl(1.5, 5, (44.5, y, z), (1, 0, 0)))
        screw = fuse([cyl(1.5, 6, (45, y, z), (1, 0, 0)),
                      cyl(2.75, 3, (51, y, z), (1, 0, 0))])
        add(f"ROTOR_SCREW_{n + 1}", screw, "buy", "M3x6 with t0.5 washer: 4.5mm engagement in5mm flange", "rotating")
        add(f"ROTOR_WASHER_{n + 1}", annulus(3, 1.6, 0.5, (50.5, y, z), (1, 0, 0)),
            "buy", "M3 flat washer OD6 t0.5", "rotating")
    add("HUB", hub, "buy", "Pololu1999 on independent shaft; 6xM3 face holes; setscrew holes not detailed", "rotating")
    add("ROTOR", rotor, "cut-drill", "SUS304 OD60 t1 ID12.10; 6x3.2 holes PCD19, deburr and inspect", "rotating")
    coupling = annulus(12.5, 3, 31, (-22.5, 0, 72), (1, 0, 0))
    add("COUPLING", coupling, "buy", "MSTS-25C-6-6 envelope; rotating screw envelope reserved diameter32", "rotating")
    add("MOTOR_SHAFT_REFERENCE", cyl(3, 15, (-29, 0, 72), (1, 0, 0)), "reference",
        "Reported shaft envelope only; D-flat axial start unknown", "reference")
    add("MOTOR_REFERENCE", cyl(27.5, 65, (-94, 0, 72), (1, 0, 0)), "reference",
        "Illustrative 55x65 motor envelope, NOT measured case dimensions", "reference")

    motor_jack = 72 - 12 - 6 - 2 - (27.5 + 1) * math.sqrt(2)
    carriage = box(-129, -45, 12 + motor_jack, 100, 90, 6)
    for y in (-30, 30):
        carriage = carriage.cut(slot(-77, y, 11 + motor_jack, 74, 3.4, 8))
    carriage = drill_z(carriage, [(x, y) for x in (-119, -39) for y in (-38, 38)])
    add("MOTOR_CARRIAGE", carriage, "PLA", "Four M3x50 jack studs, vertical setup4-24mm; saddle positions adjustable")
    for i, x in enumerate((-40, -50), 1):
        z = 18 + motor_jack
        saddle = fuse([box(x - 3, -27, z, 6, 54, 29),
                       box(x - 5, -35, z, 10, 70, 4)])
        triangle = Part.Face(Part.makePolygon([V(x - 4, -27, z + 29), V(x - 4, 0, z + 2),
                                               V(x - 4, 27, z + 29), V(x - 4, -27, z + 29)]))
        saddle = saddle.cut(triangle.extrude(V(8, 0, 0)))
        saddle = drill_z(saddle, [(x, -30), (x, 30)])
        add(f"MOTOR_V_SADDLE_{i}", saddle, "PLA",
            "90deg V with1mm NR lining; two 12mm straps, position only on stationary metal case")

    # The horizontal jaw plane avoids a solenoid-weight closing moment.
    foot = fuse([box(20, 31, 12, 60, 39, 6), box(38, 37, 18, 24, 14, 38.9),
                 box(25, 38, 56.9, 50, 12, 6),
                 box(71, 55, 18, 5, 12, 52.3), box(25, 55, 18, 5, 12, 61.7),
                 box(47.5, 58, 18, 5, 7, 64)])
    foot = drill_z(foot, [(x, y) for x in (25, 75) for y in (34, 67)])
    foot = drill_z(foot, [(30, 44), (50, 44), (70, 44)])
    for x, z, length in ((70, 67.3, 7), (24, 76.7, 7), (46, 67.3, 8), (46, 76.7, 8)):
        foot = foot.cut(cyl(1.6, length, (x, 60, z), (1, 0, 0)))
    foot = foot.cut(cyl(2.5, 8, (46, 64, 72), (1, 0, 0)))
    add("CALIPER_PEDESTAL", foot, "PLA", "Fixed vertical pivot support, axis at(50,44); 4xM3 base fixing")
    top = drill_z(box(25, 38, 81.1, 50, 12, 6), [(30, 44), (50, 44), (70, 44)])
    add("PIVOT_BRIDGE", top, "PLA", "Gap18.2 with two9mm brass bushes and0.2mm center washer")
    for i, x in enumerate((30, 70), 1):
        add(f"PIVOT_SPACER_{i}", annulus(3.5, 1.6, 18.2, (x, 44, 62.9)),
            "order-machine", "Aluminium spacer OD7 ID3.2 L18.2")
    for name, z in (("L", 62.9), ("R", 72.1)):
        add("PIVOT_BUSH_" + name, annulus(2.5, 1.6, 9, (50, 44, z)), "order-machine",
            "Brass OD5 ID3.2 L9; M3 bolt clamps tube, PLA rotates on smooth OD")
    add("PIVOT_CENTER_WASHER", annulus(4, 2.55, 0.2, (50, 44, 71.9)),
        "cut-drill", "PTFE ID5.1 OD8 t0.2")

    for side, label in ((-1, "L"), (1, "R")):
        z = 63.3 if side == -1 else 72.7
        # Output center is6.65mm from rotor center; handle is22mm on the other side.
        output_x, handle_x = 50 + side * 6.65, 50 - side * 22
        arm = fuse([bar((output_x, 24), (50, 44), 8, z, 8),
                    bar((50, 44), (handle_x, 84), 8, z, 8),
                    cyl(6, 8, (50, 44, z)),
                    box(handle_x - 8, 78, z, 16, 12, 8)])
        if side == -1:
            arm = arm.fuse(box(64, 78, z, 16, 30, 8))
        output_x = 43.35 if side == -1 else 56.65
        shoe_x = output_x if side == -1 else output_x - 4
        shoe = box(shoe_x, 18, 42, 4, 12, 60)
        arm = arm.fuse(shoe)
        arm = arm.cut(cyl(2.55, 10, (50, 44, z - 1)))
        # Pocket retains the metal shoe and has a shallow lip behind the rubber face.
        pocket_x = 46.35 if side == -1 else 52.55
        pocket = box(pocket_x, 18.9, 42.9, 1.1, 10.2, 58.2)
        arm = arm.cut(pocket)
        for bolt_z in (46, 98):
            arm = arm.cut(cyl(1.6, 6, (shoe_x - 1, 24, bolt_z), (1, 0, 0)))
        post_x = 58.25 if side == -1 else 35.75
        post = box(post_x, 61, 69, 6, 6, 6)
        arm = arm.fuse(post)
        arm = arm.cut(cyl(1.55, 32, (34, 64, 72), (1, 0, 0)))
        arm = arm.cut(cyl(2.2, 16.5, (41.75, 64, 72), (1, 0, 0)))
        if side == -1:
            arm = drill_z(arm, [(68, 104), (76, 104)])
        else:
            arm = arm.cut(cyl(1.45, 10, (28, 84, z - 1)))
        arm = arm.cut(box(48, -34, 37, 4, 68, 70))
        arm = arm.cut(box(47.35, 18.9, 66.9, 5.3, 10.2, 10.2))
        add("LEVER_" + label, arm, "PLA", "Horizontal jaw,40:20 moment arms;8mm plate plus captured pad shoe",
            "jaw_" + label)
        back_x = 46.35 if side == -1 else 52.65
        back = box(back_x, 19, 43, 1, 10, 58)
        for bolt_z in (46, 98):
            back = back.cut(cyl(1.6, 2, (back_x - .5, 24, bolt_z), (1, 0, 0)))
        add("PAD_BACK_" + label, back, "cut-drill", "A5052 t1 x10 x58; holes3.2 at3mm from ends, clear of rotor", "jaw_" + label)
        pad_x = 48.35 if side == -1 else 50.65
        add("PAD_" + label, box(pad_x, 19, 68, 1, 10, 8), "cut",
            "Hikari KGR-1100 NR;10x8x1 experimental friction insert", "jaw_" + label)
        # A1mm low-temperature spacer keeps fasteners and the lip behind the rubbing face.
        spacer_x = 47.35 if side == -1 else 51.65
        add("PAD_SPACER_" + label, box(spacer_x, 19, 67, 1, 10, 10), "cut",
            "G10/FR4 t1 heat-spreading stand-off, adhesive layer included in final gap setup", "jaw_" + label)

    # Solenoid body clamp belongs to the left jaw; no unknown M3 blind-hole depth is used.
    cradle = fuse([box(43, 67, 71.3, 37, 41, 5),
                   box(43, 67, 76.3, 37, 6, 19),
                   box(43, 95, 76.3, 37, 6, 19)])
    cradle = drill_z(cradle, [(x, y) for x in (48, 74) for y in (70, 98)])
    cradle = drill_z(cradle, [(68, 104), (76, 104)])
    for x in (48, 74):
        for y in (70, 98):
            cradle = cradle.cut(cyl(3.3, 3, (x, y, 71.3)))
    add("SOLENOID_CRADLE", cradle, "PLA", "22x30.4x18 body clamp on jawL; slot-adjust to1.5mm open stroke", "jaw_L")
    cap = drill_z(box(43, 67, 95.3, 37, 34, 4), [(x, y) for x in (48, 74) for y in (70, 98)])
    add("SOLENOID_CAP", cap, "PLA", "Ventilated low-force body restraint;4xM3x30 through nuts", "jaw_L")
    add("SOLENOID_THERMAL_PAD", box(45, 73, 76.3, 30.4, 22, 1), "cut",
        "G10/FR4 t1 stand-off, check PLA under clamp remains<40C", "jaw_L")
    add("SOLENOID_REFERENCE", box(45, 73, 77.3, 30.4, 22, 18), "reference",
        "CA0830 body envelope;48ohm12V continuous catalog rating", "jaw_L")
    plunger = cyl(4, 13, (33.5, 84, 86.3), (1, 0, 0))
    plunger = plunger.cut(box(33, 79, 85.25, 8, 10, 2.1))
    plunger = plunger.cut(cyl(1.5, 10, (38, 84, 81.3)))
    add("PLUNGER_REFERENCE", plunger, "reference",
        "Independent clevis envelope: slot2.1, hole3; hidden end inside body is illustrative", "link")
    link = drill_z(box(25, 81, 85.55, 15.5, 6, 1.5), [(28, 84), (38, 84)], 1.45)
    add("SOLENOID_LINK", link, "cut-drill", "A5052 t1.5,15.5x6;10mm hole centers;2.8mm clevis pins", "link")
    add("LINK_SPACER", annulus(3, 1.45, 4.85, (28, 84, 80.7)), "order-machine",
        "Brass OD6 ID2.9 L4.85, aligns right jaw link with solenoid axisZ86.3", "jaw_R")
    for i, x, length, z in ((1, 28, 18, 72), (2, 38, 12, 82)):
        pin = fuse([cyl(1.4, length, (x, 84, z)), cyl(2.5, 1, (x, 84, z - 1))])
        pin = pin.cut(cyl(.4, 4, (x - 2, 84, z + length - 1), (1, 0, 0)))
        add(f"LINK_PIN_{i}", pin, "order-machine",
            f"Smooth dia2.8 x{length};head5x1;crosshole0.8 at1mm from tip;0.6wire keeper", "link")
    add("RETURN_SPRING_ENVELOPE", annulus(2, 1.7, 16.5, (41.75, 64, 72), (1, 0, 0)),
        "reference", "12-0423: free20,installed16.5,k0.13; coil envelope only", "link")
    add("SPRING_GUIDE", cyl(1.25, 25, (37.5, 64, 72), (1, 0, 0)), "order-machine",
        "Smooth2.5x25; captured loose in3.1 holes, not threaded bearing surface", "link")

    sensor_base = drill_z(box(55, -48, 12, 28, 22, 6), [(69, -44), (69, -30)])
    upright = box(68, -42, 18, 8, 9, 70)
    for z in (65, 79):
        upright = upright.cut(cyl(1.7, 10, (67, -37, z), (1, 0, 0)))
    add("SENSOR_STAND", sensor_base.fuse(upright), "PLA", "Axial gap1-5mm by slots; translate pocket to align optical spot")
    pocket = box(56.7, -41, 60, 3, 35, 24)
    pocket = pocket.fuse(box(52.5, -34.1, 65.8, 4.2, 20.6, 1.5))
    pocket = pocket.fuse(box(52.5, -34.1, 76.7, 4.2, 20.6, 1.5))
    for z in (65, 79):
        pocket = pocket.cut(cyl(1.6, 10, (51, -37, z), (1, 0, 0)))
    add("SENSOR_POCKET", pocket, "PLA", "MAKER-REFLECT board retained by nonconductive strap; do not force M3 through board")
    add("SENSOR_REFERENCE", box(52.5, -31.6, 67.8, 4.2, 18.1, 8.4), "reference",
        "Board length radial, header outward; optical spot radius16 by calibration, face gap2")
    for i, z in enumerate((65, 79), 1):
        bolt = fuse([cyl(1.5, 30, (56.2, -37, z), (1, 0, 0)),
                     cyl(2.75, 3, (53.2, -37, z), (1, 0, 0))])
        add(f"SENSOR_ADJUST_BOLT_{i}", bolt, "buy",
            "M3x30, head toward rotor but radius37 outside disc; jam nuts set1-5mm gap")

    # Guard panels are cut from3mm polycarbonate; they are not rated fragment containment.
    guard_specs = [
        ("GUARD_TOP", (-143, -53, 124, 271, 166, 3)),
        ("GUARD_LEFT", (-143, -50, 12, 3, 160, 112)),
        ("GUARD_RIGHT", (125, -50, 12, 3, 160, 112)),
        ("GUARD_FRONT", (-143, -53, 12, 271, 3, 112)),
        ("GUARD_BACK", (-143, 110, 12, 271, 3, 112)),
    ]
    for name, dims in guard_specs:
        panel = box(*dims)
        if name in ("GUARD_LEFT", "GUARD_RIGHT"):
            for y in (-40, 100):
                for z in (22, 65, 114):
                    panel = panel.cut(cyl(1.7, 5, (dims[0] - 1, y, z), (1, 0, 0)))
            if name == "GUARD_LEFT":
                panel = panel.cut(cyl(8, 5, (dims[0] - 1, 0, 30), (1, 0, 0)))
        elif name in ("GUARD_FRONT", "GUARD_BACK"):
            for x in (-130, 115):
                panel = panel.cut(cyl(1.7, 5, (x, dims[1] - 1, 65), (0, 1, 0)))
        else:
            panel = drill_z(panel, [(x, y) for x in (-130, 115) for y in (-40, 100)], 1.7)
        add(name, panel, "cut-drill", "Polycarbonate3mm; template and12 aluminium angles; not rated containment")
    for side, wall in (("L", -140), ("R", 125)):
        for end, y in (("F", -40), ("B", 100)):
            x0 = wall if side == "L" else wall - 20
            wall_x = wall if side == "L" else wall - 2
            hole_x = wall + (10 if side == "L" else -10)
            for height, z0 in (("BASE", 12), ("TOP", 104)):
                horizontal_z = z0 if height == "BASE" else z0 + 18
                angle = fuse([box(wall_x, y - 10, z0, 2, 20, 20),
                              box(x0, y - 10, horizontal_z, 20, 20, 2)])
                angle = angle.cut(cyl(1.7, 4, (hole_x, y, horizontal_z - 1)))
                angle = angle.cut(cyl(1.7, 4, (wall_x - 1, y, z0 + 10), (1, 0, 0)))
                add(f"GUARD_ANGLE_{side}{end}_{height}", angle, "cut-drill",
                    "Aluminium angle20x20x2,cut width20; two3.4 holes at leg10,width10")
            ywall = -50 if end == "F" else 110
            y0 = ywall if end == "F" else ywall - 20
            wall_y = ywall if end == "F" else ywall - 2
            angle = fuse([box(wall_x, y0, 55, 2, 20, 20), box(x0, wall_y, 55, 20, 2, 20)])
            angle = angle.cut(cyl(1.7, 4, (wall_x - 1, y, 65), (1, 0, 0)))
            angle = angle.cut(cyl(1.7, 4, (hole_x, wall_y - 1, 65), (0, 1, 0)))
            add(f"GUARD_ANGLE_{side}{end}_MID", angle, "cut-drill",
                "Same20x20x2 angle,20long; corner junction")
    return parts, base_holes, holes


JOINTS = [
    ("Rotor to hub", "M3x6", 6, 1.5, 4.5, "M3 flat washer t0.5 x6; Pololu face flange5"),
    ("Bearing caps", "M3x25", 8, 16, 2.4, "2 washers and1 nut each;5.6mm nominal projection"),
    ("Bearing feet to base", "M3x20", 4, 14, 2.4, "Underside nut pocket4 deep;2 washers;projection2.6"),
    ("Caliper foot to base", "M3x20", 4, 14, 2.4, "Underside nut pocket4 deep;2 washers;projection2.6"),
    ("Motor jacks", "M3x50", 4, 12, 0, "4 nuts and3 washers per stud; setting4-24 above base"),
    ("Motor V saddles", "M3x16", 4, 10, 2.4, "2 washers and1 nut each"),
    ("Pivot bridge/bush axis", "M3x35", 3, 30.2, 2.4, "2 washers and1 nut each; never clamp PLA moving faces"),
    ("Solenoid body clamp", "M3x30", 4, 25, 2.4, "Nut pocket3 deep in cradle;1 washer;projection2.1"),
    ("Cradle to lever", "M3x20", 2, 13, 2.4, "2 washers andnut each; holes outside solenoid body"),
    ("Pad backing clamps", "M3x10", 4, 4, 2.4, "2 washers; screw heads outside rotor diameter"),
    ("Open stops", "M3x25", 2, 5, 2.4, "2 jam nuts per stop; tip setting by feeler"),
    ("Close stops", "M3x20", 2, 6, 2.4, "2 jam nuts per stop; limit to0.8deg"),
    ("Sensor foot to base", "M3x20", 2, 14, 2.4, "Underside nut pocket4 deep;2 washers"),
    ("Sensor pocket adjustment", "M3x30", 2, 19.3, 2.4, "2 M3 thin1.8 jam nuts in8.3mm gap;2 washers;1 full nut"),
    ("Guard angles/panels", "M3x10", 20, 5, 2.4, "2 wide washers OD9 t0.8 each; panel3 + angle2"),
    ("Guard angles/base", "M3x20", 4, 14, 2.4, "2 wide washers each; base12 + angle2"),
]


def physics(rotor):
    rho = 7.93e-6  # kg/mm3, nominal SUS304 density, not a material certificate.
    mass = rotor.Volume * rho
    inertia = rotor.MatrixOfInertia.A11 * rho * 1e-6
    torque_nominal = 2 * .2 * 1.5 * .024
    torque_floor = 2 * .2 * 1.5 * .019
    attached_bound = 4e-5
    return {
        "assumptions": "SUS304 density7930kg/m3, cp500J/kgK; mu0.2 is a test assumption, not a rubber rating",
        "rotor_mass_kg": mass, "rotor_inertia_kg_m2": inertia,
        "rotor_energy_J": {str(n): .5 * inertia * (n * math.pi / 30)**2 for n in (150, 300)},
        "attached_inertia_budget_kg_m2": attached_bound,
        "motor_rotor_inertia_kg_m2": None,
        "motor_inertia_bound_method": "Use total motor mass M and maximum radial envelope R: I_motor<=M*R^2; no internal disassembly",
        "rpm_ceiling_method": "min(300,60/(2*pi)*sqrt(2*0.1/(4e-5+M*R^2)))",
        "illustrative_bound_not_measurement": {"total_motor_mass_kg": .3, "max_radial_envelope_m": .05,
            "energy_at_150rpm_J": .5 * (.3 * .05**2 + attached_bound) * (5 * math.pi)**2},
        "total_energy_budget_J": .1,
        "total_inertia_budget_at_300rpm_kg_m2": .2 / (10 * math.pi)**2,
        "motor_inertia_allowance_at_300rpm_kg_m2": .2 / (10 * math.pi)**2 - attached_bound,
        "torque_nominal_Nm": torque_nominal, "torque_conservative_radius_Nm": torque_floor,
        "energy_budget_stop_time_s_at_300rpm": (.2 / (10 * math.pi)**2) * (10 * math.pi) / torque_floor,
        "rotor_mean_temperature_rise_if_0_1J_all_in_rotor_C": .1 / (mass * 500),
        "pad_pressure_at_1_5N_MPa": 1.5 / 80,
        "pad_temperature_screen_C": "NR pad mass>=0.08g, cp assumed1500J/kgK:0.1J/one pad <=0.84C average; flash heating unknown",
        "solenoid_cold_current_A": 12 / 48, "solenoid_cold_power_W": 12**2 / 48,
    }


def validate(parts):
    by_id = {p["id"]: p for p in parts}
    checks = {}
    for p in parts:
        if not p["shape"].isValid() or len(p["shape"].Solids) != 1:
            raise ValueError("Invalid solid: " + p["id"])
    checks["positive_valid_solids"] = len(parts)
    exempt = {frozenset(("SOLENOID_REFERENCE", "PLUNGER_REFERENCE"))}
    pairs = 0
    for i, first in enumerate(parts):
        a = bounds(first["shape"])
        for second in parts[i + 1:]:
            b = bounds(second["shape"])
            if any(a[k + 3] <= b[k] + 1e-6 or b[k + 3] <= a[k] + 1e-6 for k in range(3)):
                continue
            pairs += 1
            if frozenset((first["id"], second["id"])) in exempt:
                continue
            volume = first["shape"].common(second["shape"]).Volume
            if volume > 1e-5:
                raise ValueError(f"Assembled interference: {first['id']}/{second['id']} {volume:g}mm3")
    checks["assembled_aabb_candidate_pairs_checked"] = pairs
    checks["reference_overlap_exemption"] = "Only hidden plunger inside illustrative solenoid body"
    rotor = by_id["ROTOR"]["shape"]
    assert abs(bounds(rotor)[0] - 49.5) < 1e-6 and abs(bounds(rotor)[3] - 50.5) < 1e-6
    for name in ("PAD_L", "PAD_R"):
        distance = rotor.distToShape(by_id[name]["shape"])[0]
        if abs(distance - .15) > 1e-6:
            raise ValueError("Nominal pad gap mismatch")
    checks["open_pad_center_gap_mm"] = .15
    checks["coupling_engagement_each_mm"] = 8.5
    checks["motor_shoulder_clearance_mm"] = 6.5
    checks["shaft_support_span_mm"] = 64
    checks["rotor_screw_engagement_mm"] = 4.5
    checks["rotor_screw_tip_clearance_to_back_of_hub_mm"] = .5
    sweeps = []
    for step in range(41):
        angle = step * .02
        link = linkage(angle)
        if not .3 <= link["stroke_mm"] <= 1.500001:
            raise ValueError("Solenoid stroke outside chosen operating window")
        left = pivoted(by_id["LEVER_L"]["shape"], angle)
        right = pivoted(by_id["LEVER_R"]["shape"], -angle)
        if left.common(right).Volume > 1e-6:
            raise ValueError("Jaw levers collide")
        for label, theta in (("L", angle), ("R", -angle)):
            for name in ("LEVER_", "PAD_BACK_", "PAD_SPACER_"):
                moving = pivoted(by_id[name + label]["shape"], theta)
                if rotor.common(moving).Volume > 1e-6:
                    raise ValueError("Nonfriction part strikes rotor: " + name + label)
            for part in parts:
                if part["group"] != "jaw_" + label:
                    continue
                moving = pivoted(part["shape"], theta)
                a = bounds(moving)
                for fixed in parts:
                    if fixed["group"] not in ("fixed", "rotating"):
                        continue
                    if part["id"] == "PAD_" + label and fixed["id"] == "ROTOR":
                        continue
                    b = bounds(fixed["shape"])
                    if any(a[k + 3] <= b[k] + 1e-6 or b[k + 3] <= a[k] + 1e-6 for k in range(3)):
                        continue
                    if moving.common(fixed["shape"]).Volume > 1e-5:
                        raise ValueError(f"Motion interference at{angle}: {part['id']}/{fixed['id']}")
        sweeps.append({"angle_deg": angle, **link})
        pose = posed_parts(parts, angle)
        for i, first in enumerate(pose):
            a = bounds(first["shape"])
            for second in pose[i + 1:]:
                if first["group"] in ("fixed", "rotating", "reference") and second["group"] in ("fixed", "rotating", "reference"):
                    continue
                pair = frozenset((first["id"], second["id"]))
                if pair in exempt or pair in (frozenset(("PAD_L", "ROTOR")), frozenset(("PAD_R", "ROTOR"))):
                    continue
                b = bounds(second["shape"])
                if any(a[k + 3] <= b[k] + 1e-6 or b[k + 3] <= a[k] + 1e-6 for k in range(3)):
                    continue
                volume = first["shape"].common(second["shape"]).Volume
                if volume > 1e-5:
                    raise ValueError(f"Full linkage interference at{angle:g}: {first['id']}/{second['id']} {volume:g}mm3")
    checks["kinematic_samples"] = sweeps
    checks["motion_sample_interval_deg"] = .02
    asymmetric = []
    for left_angle in (0, .4, .8):
        for right_angle in (0, .4, .8):
            if left_angle == right_angle:
                continue
            pose = posed_parts(parts, left_angle, right_angle)
            for i, first in enumerate(pose):
                a = bounds(first["shape"])
                for second in pose[i + 1:]:
                    if first["group"] in ("fixed", "rotating", "reference") and second["group"] in ("fixed", "rotating", "reference"):
                        continue
                    pair = frozenset((first["id"], second["id"]))
                    if pair in exempt or pair in (frozenset(("PAD_L", "ROTOR")), frozenset(("PAD_R", "ROTOR"))):
                        continue
                    b = bounds(second["shape"])
                    if any(a[k + 3] <= b[k] + 1e-6 or b[k + 3] <= a[k] + 1e-6 for k in range(3)):
                        continue
                    if first["shape"].common(second["shape"]).Volume > 1e-5:
                        raise ValueError(f"Asymmetric motion interference {left_angle}/{right_angle}: {first['id']}/{second['id']}")
            asymmetric.append([left_angle, right_angle])
    checks["asymmetric_jaw_samples_deg"] = asymmetric
    checks["continuous_sweep_or_material_deformation_proof"] = False
    for name in ("GUARD_TOP", "GUARD_LEFT", "GUARD_RIGHT", "GUARD_FRONT", "GUARD_BACK"):
        distance = by_id[name]["shape"].distToShape(rotor)[0]
        if distance < 15:
            raise ValueError("Rotor guard clearance too small")
    checks["rotor_guard_clearance_min_mm"] = min(by_id[n]["shape"].distToShape(rotor)[0]
        for n in ("GUARD_TOP", "GUARD_LEFT", "GUARD_RIGHT", "GUARD_FRONT", "GUARD_BACK"))
    checks["optical_track_clear_of_screw_heads_mm"] = 13.5 - (9.5 + 3)
    checks["optical_track_clear_of_pad_radial_min_mm"] = 19 - 18.5
    checks["sensor_adjustment_mm"] = [1, 5]
    checks["minimum_sensor_jam_nut_space_mm"] = 8.3 - 3
    if checks["minimum_sensor_jam_nut_space_mm"] < 2 * 1.8 + .5:
        raise ValueError("Sensor adjustment cannot fit the jam nuts")
    if checks["optical_track_clear_of_screw_heads_mm"] <= 0 or checks["optical_track_clear_of_pad_radial_min_mm"] <= 0:
        raise ValueError("Sensing track overlaps friction or screws")
    checks["physical_approval"] = False
    return checks


def dxf_circles(path, circles, outline=None):
    rows = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
            "0", "SECTION", "2", "ENTITIES"]
    for x, y, r in circles:
        rows += ["0", "CIRCLE", "8", "CUT", "10", str(x), "20", str(y), "30", "0", "40", str(r)]
    if outline:
        rows += ["0", "LWPOLYLINE", "8", "CUT", "90", str(len(outline)), "70", "1"]
        for x, y in outline:
            rows += ["10", str(x), "20", str(y)]
    rows += ["0", "ENDSEC", "0", "EOF"]
    path.write_text("\n".join(rows) + "\n")


def svg(path, width, height, content):
    content = re.sub(r"(<text\b[^>]*>)(.*?)(</text>)",
                     lambda m: m[1] + escape(m[2], quote=False) + m[3], content, flags=re.S)
    text = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" '
            f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>'
            '<style>text{font-family:sans-serif;font-size:3px} .note{font-size:2.7px}'
            '.cut{fill:none;stroke:#172b4d;stroke-width:.25}.dim{stroke:#777;stroke-width:.15}</style>'
            + content + "</svg>\n")
    ET.fromstring(text)
    path.write_text(text)


def drawings(parts, base_holes, holes):
    body = '<text x="8" y="8">R1 / SUS304 t1 / mm / NOMINAL PROTOTYPE - NOT QUALIFIED</text>'
    body += '<g transform="translate(48 48)">'
    for x, y, r in [(0, 0, 30), (0, 0, P["rotor_id_mm"] / 2), *[(x, y, 1.6) for x, y in holes]]:
        body += f'<circle class="cut" cx="{x}" cy="{y}" r="{r}"/>'
    body += '<circle class="dim" fill="none" stroke-dasharray="1 1" r="9.5"/></g>'
    for i, line in enumerate(("OD60 +/-0.10; ID12.10 +0.05/0", "6 x diameter3.2 +/-0.05; PCD19; equally spaced60deg",
                               "Hole true position target0.10; t1 +/-0.05", "Deburr R0.2 edges; do not round friction face",
                               "After mount: axial TIR<=0.10, radial TIR<=0.15mm", "6 x M3x6 +0.5 washer; engagement4.5 in5mm hub",
                               "NR pads at radius19-29; optical track13.5-18.5 on other sector",
                               "Cutting / drilling required. No stock rotor is implied.")):
        body += f'<text x="8" y="{86 + i * 5}">{line}</text>'
    svg(OUT / "rotor-drawing.svg", 150, 130, body)
    dxf_circles(OUT / "rotor-cut.dxf", [(0, 0, 30), (0, 0, P["rotor_id_mm"] / 2),
                                     *[(x, y, 1.6) for x, y in holes]])
    base = '<text x="8" y="8">BASE: plywood290 x180 x12; all holes3.4; origin lower-left(-150,-60)</text>'
    base += '<rect class="cut" x="10" y="15" width="290" height="180"/>'
    for x, y in base_holes:
        base += f'<circle class="cut" cx="{x + 160}" cy="{y + 75}" r="1.7"/>'
        base += f'<text x="{x + 162}" y="{y + 74}" class="note">{x},{y}</text>'
    base += '<text x="10" y="205">Under bearing/caliper/sensor holes: underside dia8 counterbore4 deep. All coordinates are nominal.</text>'
    svg(OUT / "base-drill.svg", 315, 212, base)
    track = '<g transform="translate(24 24)">'
    for i in range(24):
        a, b = math.radians(i * 15), math.radians((i + 1) * 15)
        pts = [(r * math.cos(t), r * math.sin(t)) for r, t in ((18.5, a), (18.5, b), (13.5, b), (13.5, a))]
        track += (f'<path d="M{pts[0][0]},{pts[0][1]} A18.5,18.5 0 0 1 {pts[1][0]},{pts[1][1]} '
                  f'L{pts[2][0]},{pts[2][1]} A13.5,13.5 0 0 0 {pts[3][0]},{pts[3][1]} Z" '
                  f'fill="{"black" if i % 2 == 0 else "white"}"/>')
    track += '<circle r="18.5" class="cut"/><circle r="13.5" class="cut"/></g>'
    svg(OUT / "sensor-track.svg", 48, 48, track)
    layout = '<text x="8" y="8">R1 nominal layout / X along shaft, Y sideways / all dimensions mm</text>'
    colors = {"PLA": "#bbdfd0", "buy": "#c7d5e8", "cut-drill": "#ebd9b4", "cut": "#ddd",
              "order-machine": "#c7d5e8", "reference": "#eee"}
    layout += '<g transform="translate(160 75)">'
    for p in parts:
        if p["id"].startswith(("GUARD_", "BASE", "MOTOR_REFERENCE")):
            continue
        if p["id"].startswith("GUARD_ANGLE"):
            continue
        for edge in p["shape"].Edges:
            points = edge.discretize(Deflection=.15)
            path = " ".join(f"{v.x:.3f},{v.y:.3f}" for v in points)
            layout += f'<polyline points="{path}" fill="none" stroke="#345" stroke-width=".16"/>'
    layout += '<line x1="-145" y1="0" x2="125" y2="0" stroke="#c33" stroke-width=".2" stroke-dasharray="2 2"/></g>'
    labels = [("Motor V saddle / shaft A6 B15", 18, 28), ("Coupling L31 / each insertion8.5", 100, 35),
              ("626ZZ centers24,88 / span64", 170, 28), ("Rotor X50 / OD60 / Z72", 200, 45),
              ("Horizontal jaws: pivot(50,44), padsY24", 165, 184),
              ("Solenoid body on left jaw;40:20 leverage", 165, 191),
              ("Cover inside X[-140,125],Y[-50,110], topZ124", 8, 206),
              ("Reference envelopes are not vendor CAD or measured motor geometry.", 8, 213)]
    for text, x, y in labels:
        layout += f'<text x="{x}" y="{y}">{text}</text>'
    svg(OUT / "layout.svg", 310, 220, layout)
    detail = '<text x="10" y="10">R1 / CUSTOM PARTS / mm / nominal prototype dimensions</text>'
    detail += '<rect class="cut" x="20" y="24" width="100" height="6"/>'
    detail += '<text x="20" y="20">SUS303 ground shaft: diameter6 g6 x100 +/-0.1, C0.2 ends. Qty1</text>'
    detail += '<rect class="cut" x="20" y="48" width="10" height="58"/>'
    for y in (51, 103):
        detail += f'<circle class="cut" cx="25" cy="{y}" r="1.6"/>'
    detail += '<text x="40" y="58">A5052 pad backplate:10 x58 x1. Qty2</text>'
    detail += '<text x="40" y="64">2 holes dia3.2; centers(5,3),(5,55). End spacing52.</text>'
    detail += '<text x="40" y="70">Mount screw heads lie outside rotor perimeter.</text>'
    detail += '<text x="40" y="76">Central G10 spacer10 x10 x1, NR pad10 x8 x1.</text>'
    detail += '<text x="40" y="82">NR is an experimental friction material, not brake-rated.</text>'
    detail += '<text x="40" y="88">Adhesive only on stationary inserts; retain in printed pocket.</text>'
    detail += '<rect class="cut" x="20" y="120" width="15.5" height="6"/>'
    for x in (23, 33):
        detail += f'<circle class="cut" cx="{x}" cy="123" r="1.45"/>'
    lines = [
        "A5052 link:15.5 x6 x1.5; holes dia2.9 at(3,3),(13,3); qty1.",
        "Pin: dia2.8 -0.03/0, shaft lengths18 and12, qty1 each.",
        "Pin head dia5 x1; cross-hole0.8 at1 from tip;0.6 wire keeper.",
        "Pivot bushes: brass OD5 ID3.2 L9 +/-0.05; qty2.",
        "Bridge spacers: aluminium OD7 ID3.2 L18.2 +/-0.05; qty2.",
        "Link spacer: brass OD6 ID2.9 L4.85 +/-0.05; qty1.",
        "Return guide: smooth stainless dia2.5 x25; qty1.",
        "Thrust shims: ID6.1 OD8.5 t0.3; qty2. Center PTFE ID5.1 OD8 t0.2; qty1.",
        "Solenoid stand-off: G10/FR4 30.4 x22 x1; qty1.",
        "Guard:12 pieces of20x20x2 aluminium angle, each20 wide.",
        "Each angle: one hole dia3.4 in each leg,10 from edge and10 from end.",
        "Do not drill or modify the owned motor. These custom parts require fabrication.",
    ]
    for i, line in enumerate(lines):
        detail += f'<text x="10" y="{139 + i * 7}">{line}</text>'
    svg(OUT / "machine-parts.svg", 215, 230, detail)
    dxf_circles(OUT / "pad-back-cut.dxf", [(5, 3, 1.6), (5, 55, 1.6)],
                [(0, 0), (10, 0), (10, 58), (0, 58)])
    dxf_circles(OUT / "link-cut.dxf", [(3, 3, 1.45), (13, 3, 1.45)],
                [(0, 0), (15.5, 0), (15.5, 6), (0, 6)])
    for name, w, h, positions in [
        ("guard-top", 271, 166, [(13, 13), (258, 13), (13, 153), (258, 153)]),
        ("guard-end", 160, 112, [(y, z) for y in (10, 150) for z in (10, 53, 102)]),
        ("guard-side", 271, 112, [(13, 53), (258, 53)]),
    ]:
        circles = [(x, y, 1.7) for x, y in positions]
        dxf_circles(OUT / (name + "-cut.dxf"), circles, [(0, 0), (w, 0), (w, h), (0, h)])
    guard = '<text x="8" y="8">GUARD / PC3mm / dimensions refer to cut outlines; assembled inside clearances, NOT impact rating</text>'
    for i, line in enumerate([
        "Top271 x166 qty1; holes(13,13),(258,13),(13,153),(258,153).",
        "End160 x112 qty2; holes U10/150 x V10/53/102 (6 per panel).",
        "Left end only: additional dia16 cable grommet hole U50,V18; ID10 grommet.",
        "Side271 x112 qty2; holes(13,53),(258,53). All screw holes dia3.4.",
        "Coordinates are from each blank lower-left. End UV=(Y,Z), side=(X,Z).",
        "12 aluminium20x20x2 angles,20long;4 base,4 middle corners,4 lid.",
        "20 x M3x10 at panels;4 x M3x20 at base. Wide washers OD9 t0.8 both faces.",
        "Keep lid screwed shut while rotating. No claim of fragment containment.",
        "Do not scale screenshot dimensions; DXF unit code is mm.",
    ]):
        guard += f'<text x="8" y="{23 + i * 8}">{line}</text>'
    svg(OUT / "guard-drawing.svg", 220, 100, guard)
    assembly_picture(parts)


def assembly_picture(parts):
    palette = {"PLA": "#91c5ab", "buy": "#90a8c0", "cut-drill": "#cec3a7",
               "cut": "#405464", "order-machine": "#aebdca", "reference": "#b0b0b0"}
    triangles = []
    for p in parts:
        if p["id"].startswith("GUARD_") or p["id"] == "BASE":
            continue
        vertices, faces = p["shape"].tessellate(.5)
        for face in faces:
            points = [vertices[i] for i in face]
            depth = sum(v.x - v.y + v.z for v in points) / 3
            coords = [(math.sqrt(.5) * (v.x + v.y), .408248 * (v.x - v.y) - .816497 * v.z) for v in points]
            normal = (points[1] - points[0]).cross(points[2] - points[0])
            shade = .55 + .45 * abs(normal.dot(V(.3, -.4, .866))) / max(normal.Length, 1e-12)
            base = palette[p["process"]].lstrip("#")
            color = "#" + "".join(f"{min(255,round(int(base[i:i+2],16)*shade)):02x}" for i in (0, 2, 4))
            triangles.append((depth, coords, color))
    projected = [v for _, points, _ in triangles for v in points]
    x0, y0 = min(p[0] for p in projected), min(p[1] for p in projected)
    x1, y1 = max(p[0] for p in projected), max(p[1] for p in projected)
    scale = min(270 / (x1 - x0), 165 / (y1 - y0))
    image = '<text x="8" y="10">PICO BRAKE R1 / Original nominal assembly / guard hidden for explanation</text>'
    for _, points, color in sorted(triangles, key=lambda row: row[0]):
        coords = " ".join(f"{(x-x0)*scale+12:.2f},{(y-y0)*scale+22:.2f}" for x, y in points)
        image += f'<polygon points="{coords}" fill="{color}" stroke="{color}" stroke-width=".04"/>'
    image += '<text x="8" y="205">Independent shaft / opposed horizontal jaws / motor case is illustrative; dimensional fit is not physical qualification.</text>'
    svg(OUT / "assembly-view.svg", 300, 214, image)


def export(parts, checks, base_holes, holes):
    OUT.mkdir(parents=True, exist_ok=True)
    stldir = OUT / "stl"
    stldir.mkdir(exist_ok=True)
    records = []
    doc = App.newDocument("PrototypeR1")
    objects = []
    for p in parts:
        shape = p["shape"]
        expected = {"bbox_mm": bounds(shape), "center_of_mass_mm": list(shape.CenterOfMass)}
        obj = doc.addObject("Part::Feature", p["id"])
        obj.Shape = shape
        objects.append(obj)
        row = {key: value for key, value in p.items() if key != "shape"}
        row.update(expected, volume_mm3=shape.Volume)
        if p["process"] == "PLA":
            local = moved(shape, (-expected["bbox_mm"][0], -expected["bbox_mm"][1], -expected["bbox_mm"][2]))
            mesh = MeshPart.meshFromShape(Shape=local, LinearDeflection=.08, AngularDeflection=.12, Relative=False)
            filename = "stl/" + p["id"].lower() + ".stl"
            mesh.write(str(OUT / filename))
            reloaded = Mesh.Mesh(str(OUT / filename))
            if not reloaded.isSolid() or abs(reloaded.Volume - local.Volume) / local.Volume > .01:
                raise ValueError("STL round-trip volume/closure failed: " + p["id"])
            verts, faces = reloaded.Topology
            volume, center = mesh_moments([list(v) for v in verts], faces)
            if math.dist(center, list(local.CenterOfMass)) > .08:
                raise ValueError("STL centroid mismatch: " + p["id"])
            row["stl"] = filename
            row["stl_volume_error_fraction"] = abs(volume - local.Volume) / local.Volume
        records.append(row)
    doc.recompute()
    with tempfile.TemporaryDirectory(prefix="prototype-step-") as temp:
        raw = Path(temp) / "raw.step"
        Import.export(objects, str(raw))
        text = raw.read_text()
        # Preserve the shared sanitized STEP identity without changing the frozen C08 scanner.
        header = "FILE_NAME('public-brake.step','2026-11-14T00:00:00',(''),(''),'Open CASCADE','FreeCAD','');"
        text, count = re.subn(r"FILE_NAME\s*\(.*?\)\s*;", lambda _: header, text, count=1, flags=re.S)
        if count != 1:
            raise ValueError("Unexpected STEP header")
        (OUT / "prototype-mechanical.step").write_text(text)
    readback = App.newDocument("PrototypeReadback")
    Import.insert(str(OUT / "prototype-mechanical.step"), readback.Name)
    shapes = [o for o in readback.Objects if hasattr(o, "Shape") and o.Shape.Solids]
    lookup = {o.Label: o for o in shapes}
    for row in records:
        if row["id"] not in lookup:
            raise ValueError("STEP identity missing: " + row["id"])
        shape = lookup[row["id"]].Shape
        if len(shape.Solids) != 1:
            raise ValueError("STEP solid count mismatch: " + row["id"])
        require_pose(bounds(shape), list(shape.Solids[0].CenterOfMass), row, row["id"], .001, .001)
        if abs(shape.Volume - row["volume_mm3"]) / row["volume_mm3"] > .0001:
            raise ValueError("STEP volume mismatch: " + row["id"])
    checks["step_readback_shapes"] = len(records)
    App.closeDocument(readback.Name)
    App.closeDocument(doc.Name)
    drawings(parts, base_holes, holes)
    with (OUT / "joints.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["joint", "screw", "quantity", "grip_mm", "thread_engagement_mm", "note"])
        writer.writerows(JOINTS)
    report = {"schema": "prototype-mechanical-r1", "status": "PASS", "parameters": P,
              "nominal_geometry_ready": True, "physical_ready": False,
              "scope": "Original geometry and nominal fit only; no manufacturer's CAD copied",
              "checks": checks, "physics": physics(next(p["shape"] for p in parts if p["id"] == "ROTOR")),
              "parts": records, "fastener_totals": {}}
    for _, screw, qty, *_ in JOINTS:
        report["fastener_totals"][screw] = report["fastener_totals"].get(screw, 0) + qty
    report["files"] = [{"path": str(path.relative_to(OUT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                       for path in sorted(OUT.rglob("*")) if path.is_file()
                       and path.name not in ("manifest.json", "prototype-mechanical.zip")]
    (OUT / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    with zipfile.ZipFile(OUT / "prototype-mechanical.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.rglob("*")):
            if path.is_file() and path.suffix != ".zip":
                archive.write(path, str(path.relative_to(OUT)))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    parts, base_holes, holes = build()
    checks = validate(parts)
    report = export(parts, checks, base_holes, holes)
    print(json.dumps({"status": report["status"], "parts": len(parts),
                      "printable_parts": sum(p["process"] == "PLA" for p in parts),
                      "physics": report["physics"], "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
