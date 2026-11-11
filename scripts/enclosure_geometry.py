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
    for axis in range(3):
        pin = Part.makeCylinder(1.5, 6.7, point_on_axis(axis, 62.3, REGISTER), axis_vector(axis))
        shape = shape.fuse(pin)
    for axis in range(3):
        bore = Part.makeCylinder(THREAD_MINOR, THREAD_DEPTH + .0001,
                                 point_on_axis(axis, FRAME_INNER + .0001, CORNER_FIXING), axis_vector(axis, -1))
        shape = shape.cut(bore)
    return shape.removeSplitter()


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
            "length_including_head_mm": CORNER_SCREW_LENGTH, "frame_grip_mm": 5.2,
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
    return shape


def signed_corner(signs):
    matrix = App.Matrix()
    permutation = (0, 1, 2) if math.prod(signs) > 0 else (1, 0, 2)
    for i in range(3):
        for j in range(3):
            setattr(matrix, f"A{i+1}{j+1}", signs[i] if permutation[i] == j else 0)
    shape = corner_positive()
    shape.transformShape(matrix)
    return shape


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
                        "length_including_head_mm": 10, "frame_grip_mm": 5.2, "engagement_mm": 4.8,
                        "tap_depth_mm": 5.5, "bottom_margin_mm": .7, "tightening_torque_Nm": None,
                        "material_assumption": "Machined 6061-T6 frame/corner; material and strength unqualified",
                        "physical_ready": False,
                    })
    return shapes, joints
