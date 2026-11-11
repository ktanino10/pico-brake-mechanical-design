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
            "material_assumption": "Machined 6061-T6 frame/corner; certification and strength unqualified",
            "tightening_torque_Nm": None, "physical_ready": False,
        })
    return shapes, joints
