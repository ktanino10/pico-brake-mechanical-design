"""Independent nominal enclosure primitives; no original CAD/STL contour is read."""
import math

import FreeCAD as App
import Part

# Source reference: +/-69 enclosure, +/-68 frame outside, PCD153 corner fixing.
# New assumptions: uniform 5.2 metal frame, tapped corner, integral locating pins.
OUTER = 69.0
FRAME_OUTER = 68.0
FRAME_INNER = 62.8
CORNER_INNER = 50.8
CORNER_FIXING = 76.5 / math.sqrt(2)
REGISTER = 58.5
FRAME_EDGE_GAP = 0.2
THREAD_MINOR = 1.25
THREAD_MAJOR = 1.5
THREAD_DEPTH = 5.5
CORNER_SCREW_LENGTH = 10.0
DIAGONAL_SEAT = 60.8
CAP_SEAT = 66.0
DIAGONAL = App.Vector(1, 1, 1)
DIAGONAL.normalize()
CAP_GRIP = (CAP_SEAT - DIAGONAL_SEAT) * math.sqrt(3)


def above_diagonal(coordinate):
    cutter = Part.makeBox(100, 100, 100, App.Vector(-50, -50, 0))
    cutter.transformShape(App.Placement(App.Vector(coordinate, coordinate, coordinate),
                                       App.Rotation(App.Vector(0, 0, 1), DIAGONAL)).toMatrix())
    return cutter


def below_diagonal(coordinate):
    cutter = Part.makeBox(100, 100, 100, App.Vector(-50, -50, 0))
    cutter.transformShape(App.Placement(App.Vector(coordinate, coordinate, coordinate),
                                       App.Rotation(App.Vector(0, 0, 1), -DIAGONAL)).toMatrix())
    return cutter


def axis_vector(axis, sign=1):
    values = [0, 0, 0]
    values[axis] = sign
    return App.Vector(*values)


def point_on_axis(axis, coordinate, transverse):
    values = [transverse, transverse, transverse]
    values[axis] = coordinate
    return App.Vector(*values)


def corner_positive():
    shape = Part.makeBox(12, 12, 12, App.Vector(CORNER_INNER, CORNER_INNER, CORNER_INNER))
    shape = shape.cut(above_diagonal(DIAGONAL_SEAT))
    shape = shape.cut(below_diagonal(53.8))
    for axis in range(3):
        pin = Part.makeCylinder(1.5, 6.7, point_on_axis(axis, 62.3, REGISTER), axis_vector(axis))
        shape = shape.fuse(pin)
    for axis in range(3):
        bore = Part.makeCylinder(THREAD_MINOR, THREAD_DEPTH + .0001,
                                 point_on_axis(axis, FRAME_INNER + .0001, CORNER_FIXING), axis_vector(axis, -1))
        shape = shape.cut(bore)
    diagonal_bore = Part.makeCylinder(THREAD_MINOR, 5.5001,
                                     App.Vector(DIAGONAL_SEAT, DIAGONAL_SEAT, DIAGONAL_SEAT)+DIAGONAL*.0001,
                                     -DIAGONAL)
    shape = shape.cut(diagonal_bore)
    return shape.removeSplitter()


def pin_access_slot(axis):
    direction = axis_vector(axis)
    start = point_on_axis(axis, 62, REGISTER)
    end = point_on_axis(axis, 62, 54)
    perpendicular = direction.cross(end-start)
    perpendicular.normalize()
    perpendicular *= 1.65
    points = [start+perpendicular, end+perpendicular, end-perpendicular, start-perpendicular]
    bridge = Part.Face(Part.makePolygon(points+[points[0]])).extrude(direction*8)
    return bridge.fuse(Part.makeCylinder(1.65, 8, start, direction)).fuse(Part.makeCylinder(1.65, 8, end, direction))


def corner_cap_positive(open_access=True):
    outer = Part.makeBox(13, 13, 13, App.Vector(56, 56, 56))
    inner = Part.makeBox(13, 13, 13, App.Vector(55, 55, 55))
    shape = outer.cut(inner)
    base = App.Vector(DIAGONAL_SEAT, DIAGONAL_SEAT, DIAGONAL_SEAT)
    boss = Part.makeCone(2.6, 3.5, CAP_GRIP, base, DIAGONAL)
    shape = shape.fuse(boss).cut(above_diagonal(CAP_SEAT))
    shape = shape.cut(Part.makeCylinder(1.7, CAP_GRIP+.002, base-DIAGONAL*.001, DIAGONAL))
    shape = shape.cut(Part.makeCone(3, 1.5, 1.7, App.Vector(CAP_SEAT, CAP_SEAT, CAP_SEAT), -DIAGONAL))
    for axis in range(3):
        pin_void = pin_access_slot(axis) if open_access else Part.makeCylinder(1.65, 8, point_on_axis(axis, 62, REGISTER), axis_vector(axis))
        shape = shape.cut(pin_void)
        shape = shape.cut(Part.makeCylinder(3.2, 8, point_on_axis(axis, 62, CORNER_FIXING), axis_vector(axis)))
    return shape.removeSplitter()


def cap_clearance_positive():
    return Part.makeCone(2.8, 3.7, CAP_GRIP+.002,
                         App.Vector(DIAGONAL_SEAT, DIAGONAL_SEAT, DIAGONAL_SEAT)-DIAGONAL*.001, DIAGONAL)


def sign_transform(shape, signs):
    matrix = App.Matrix()
    permutation = (0, 1, 2) if math.prod(signs) > 0 else (1, 0, 2)
    for i in range(3):
        for j in range(3):
            setattr(matrix, f"A{i+1}{j+1}", signs[i] if permutation[i] == j else 0)
    result = shape.copy()
    result.transformShape(matrix)
    return result


def cut_corner_interface(shape, axis):
    inward = axis_vector(axis, -1)
    clearance = Part.makeCylinder(1.7, 5.2002,
                                  point_on_axis(axis, FRAME_OUTER + .0001, CORNER_FIXING), inward)
    seat = Part.makeCone(3, 1.5, 1.7, point_on_axis(axis, FRAME_OUTER, CORNER_FIXING), inward)
    register = Part.makeCylinder(1.65, 5.2002, point_on_axis(axis, FRAME_OUTER + .0001, REGISTER), inward)
    return shape.cut(clearance.fuse(seat).fuse(register)).removeSplitter()


def frame_end_coupon(axis):
    low, high = [50.0] * 3, [FRAME_INNER - FRAME_EDGE_GAP] * 3
    low[axis], high[axis] = FRAME_INNER, FRAME_OUTER
    stock = Part.makeBox(*(high[i] - low[i] for i in range(3)), App.Vector(*low))
    return cut_corner_interface(stock, axis)


def corner_screw(axis):
    seat = point_on_axis(axis, FRAME_OUTER, CORNER_FIXING)
    inward = axis_vector(axis, -1)
    shank = Part.makeCylinder(THREAD_MAJOR, CORNER_SCREW_LENGTH, seat, inward)
    head = Part.makeCone(3, 1.5, 1.7, seat, inward)
    return shank.fuse(head).removeSplitter()


def corner_slice():
    shapes = {"E_CORNER_PPP": corner_positive()}
    joints = []
    for axis, name in enumerate("XYZ"):
        frame_id, screw_id = "E_COUPON_" + name, "E_CORNER_SCREW_" + name
        shapes[frame_id] = frame_end_coupon(axis)
        shapes[screw_id] = corner_screw(axis)
        joints.append({
            "id": "EC_" + name, "fastener": screw_id, "clamped_part": frame_id,
            "receiver": "E_CORNER_PPP", "axis": list(axis_vector(axis, -1)),
            "seat_point_mm": list(point_on_axis(axis, FRAME_OUTER, CORNER_FIXING)),
            "seat_kind": "nominal flat-head cone D6 / height1.7",
            "nominal_thread": "M3x0.5; major/minor cylindrical representation",
            "nominal_length_mm": CORNER_SCREW_LENGTH, "length_convention": "including-head",
            "modeled_total_length_mm": CORNER_SCREW_LENGTH, "frame_grip_mm": 5.2,
            "engagement_mm": 4.8, "tap_depth_mm": THREAD_DEPTH, "bottom_margin_mm": .7,
            "thread_major_radius_mm": THREAD_MAJOR, "thread_minor_radius_mm": THREAD_MINOR,
            "material_assumption": "Machined 6061-T6 frame/corner; certification and strength unqualified",
            "tightening_torque_Nm": None, "physical_ready": False,
        })
    return shapes, joints


def case_rotation(axis):
    return App.Rotation(App.Vector(1, 1, 1), {"X": 120, "Y": 240, "Z": 0}[axis])


def case_point(point, axis):
    x, y, z = point
    return {"X": [z, x, y], "Y": [y, z, x], "Z": [x, y, z]}[axis]


def cage_frame(axis, sign):
    z = FRAME_INNER if sign > 0 else -FRAME_OUTER
    stock = Part.makeBox(136, 125.2, 5.2, App.Vector(-68, -62.6, z))
    shape = stock.cut(Part.makeCylinder(60.5, 7.2, App.Vector(0, 0, z-1)))
    if sign < 0:
        for angle in (45, 135, 225, 315):
            x, y = 63*math.cos(math.radians(angle)), 63*math.sin(math.radians(angle))
            shape = shape.fuse(Part.makeCylinder(3.5, 5.2, App.Vector(x, y, z)))
            shape = shape.cut(Part.makeCylinder(1.7, 7.2, App.Vector(x, y, z-1)))
            shape = shape.cut(Part.makeCone(3, 1.5, 1.7, App.Vector(x, y, -68)))
            shape = shape.cut(Part.makeCylinder(2.025, 1.0501, App.Vector(x, y, -63.85)))
    else:
        web = Part.makeBox(160, 12, 5.2, App.Vector(-80, -6, z))
        web.rotate(App.Vector(), App.Vector(0, 0, 1), 45)
        shape = shape.fuse(web.common(stock))
        for coordinate in (-9.7581, 36.2039):
            shape = shape.cut(Part.makeCylinder(1.7, 7.2, App.Vector(coordinate, coordinate, z-1)))
            shape = shape.cut(Part.makeCone(3, 1.5, 1.7, App.Vector(coordinate, coordinate, 68), App.Vector(0, 0, -1)))
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = App.Vector(sx*CORNER_FIXING, sy*CORNER_FIXING, sign*68)
            inward = App.Vector(0, 0, -sign)
            shape = shape.cut(Part.makeCylinder(1.7, 5.2002, p-inward*.0001, inward))
            shape = shape.cut(Part.makeCone(3, 1.5, 1.7, p, inward))
            r = App.Vector(sx*REGISTER, sy*REGISTER, sign*68)
            shape = shape.cut(Part.makeCylinder(1.65, 5.2002, r-inward*.0001, inward))
    shape = shape.removeSplitter()
    shape.transformShape(App.Placement(App.Vector(), case_rotation(axis)).toMatrix())
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                signs = (sx, sy, sz)
                if signs["XYZ".index(axis)] == sign:
                    shape = shape.cut(sign_transform(cap_clearance_positive(), signs))
    return shape


def signed_corner(signs):
    return sign_transform(corner_positive(), signs)


def frame_cage():
    shapes, joints = {}, []
    for axis in "XYZ":
        shapes["E_FRAME_MOTOR_"+axis] = cage_frame(axis, -1)
        shapes["E_FRAME_BOARD_"+axis] = cage_frame(axis, 1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                signs = (sx, sy, sz)
                label = "".join("P" if sign > 0 else "N" for sign in signs)
                corner_id = "E_CORNER_"+label
                shapes[corner_id] = signed_corner(signs)
                cap_id, cap_screw_id = "E_CORNER_CAP_"+label, "E_CAP_SCREW_"+label
                shapes[cap_id] = sign_transform(corner_cap_positive(), signs)
                cap_screw = Part.makeCylinder(THREAD_MAJOR, 14, App.Vector(CAP_SEAT, CAP_SEAT, CAP_SEAT), -DIAGONAL)
                cap_screw = cap_screw.fuse(Part.makeCone(3, 1.5, 1.7, App.Vector(CAP_SEAT, CAP_SEAT, CAP_SEAT), -DIAGONAL))
                shapes[cap_screw_id] = sign_transform(cap_screw.removeSplitter(), signs)
                joints.append({
                    "id": "EC_CAP_"+label, "fastener": cap_screw_id, "clamped_part": cap_id,
                    "receiver": corner_id, "axis": [-s/math.sqrt(3) for s in signs],
                    "seat_point_mm": [s*CAP_SEAT for s in signs],
                    "seat_kind": "nominal flat-head cone D6 / height1.7 on actual outer corner cover",
                    "nominal_thread": "M3x0.5; major/minor cylindrical representation",
                    "thread_major_radius_mm": THREAD_MAJOR, "thread_minor_radius_mm": THREAD_MINOR,
                    "nominal_length_mm": 14, "length_convention": "including-head",
                    "modeled_total_length_mm": 14, "frame_grip_mm": CAP_GRIP,
                    "engagement_mm": 14-CAP_GRIP, "tap_depth_mm": 5.5,
                    "bottom_margin_mm": 5.5-(14-CAP_GRIP), "tightening_torque_Nm": None,
                    "material_assumption": "Machined nominal metal cover/corner; outer contact safety unqualified",
                    "physical_ready": False,
                })
                for index, axis in enumerate("XYZ"):
                    sign = signs[index]
                    frame_id = "E_FRAME_"+("BOARD_" if sign > 0 else "MOTOR_")+axis
                    screw_id = "E_FRAME_SCREW_"+label+"_"+axis
                    values = [s*CORNER_FIXING for s in signs]
                    values[index] = sign*68
                    seat, inward = App.Vector(*values), axis_vector(index, -sign)
                    shank = Part.makeCylinder(THREAD_MAJOR, 10, seat, inward)
                    head = Part.makeCone(3, 1.5, 1.7, seat, inward)
                    shapes[screw_id] = shank.fuse(head).removeSplitter()
                    joints.append({
                        "id": "EC_"+label+"_"+axis, "fastener": screw_id,
                        "clamped_part": frame_id, "receiver": corner_id,
                        "axis": list(inward), "seat_point_mm": values,
                        "seat_kind": "nominal flat-head cone D6 / height1.7",
                        "nominal_thread": "M3x0.5; major/minor cylindrical representation",
                        "thread_major_radius_mm": THREAD_MAJOR, "thread_minor_radius_mm": THREAD_MINOR,
                        "nominal_length_mm": 10, "length_convention": "including-head",
                        "modeled_total_length_mm": 10, "frame_grip_mm": 5.2, "engagement_mm": 4.8,
                        "tap_depth_mm": 5.5, "bottom_margin_mm": .7, "tightening_torque_Nm": None,
                        "material_assumption": "Machined 6061-T6 frame/corner; material and strength unqualified",
                        "physical_ready": False,
                    })
    return shapes, joints
