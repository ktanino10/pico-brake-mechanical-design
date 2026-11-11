"""Independent holder ribs/bosses and mechanical interface references, not PCB designs."""
from pathlib import Path
import json
import math

import FreeCAD as App
import Part

from enclosure_geometry import FRAME_INNER, FRAME_OUTER, axis_vector

ROOT = Path(__file__).resolve().parents[1]
N = App.Vector(1, 1, 1); N.normalize()
U = App.Vector(1, 0, -1); U.normalize()
V = N.cross(U)


def on_plane(u, v, distance):
    return U*u + V*v + N*distance


def basis_matrix(x, y, z, position=None):
    matrix = App.Matrix()
    for column, vector in enumerate((x, y, z), 1):
        for row, value in enumerate(vector, 1):
            setattr(matrix, f"A{row}{column}", value)
    if position is not None:
        matrix.A14, matrix.A24, matrix.A34 = position.x, position.y, position.z
    return matrix


def plane_box(width, height, thickness, u, v, distance):
    shape = Part.makeBox(width, height, thickness, App.Vector(u, v, distance))
    shape.transformShape(basis_matrix(U, V, N))
    return shape


def rib(first, second, width=6, thickness=4):
    direction = second-first
    length = direction.Length
    direction.normalize()
    side = N.cross(direction); side.normalize()
    shape = Part.makeBox(length, width, thickness, App.Vector(0, -width/2, -thickness/2))
    shape.transformShape(basis_matrix(direction, side, N, first))
    return shape


def tube(radius, inner, height, base):
    return Part.makeCylinder(radius, height, base, N).cut(Part.makeCylinder(inner, height+.002, base-N*.001, N))


def holders(conditions=None):
    if conditions is None:
        conditions = json.loads((ROOT/"data/enclosure-nominal-conditions.json").read_text())
    if (conditions["new_frame_inner_face_abs_mm"] != FRAME_INNER or
            conditions["new_frame_outer_face_abs_mm"] != FRAME_OUTER):
        raise ValueError("Unsupported frame datum: redesign the frame and holder interfaces together")
    assumptions = conditions["new_holder_assumptions"]
    spacer_height = assumptions["spacer_height_mm"]
    washer_thickness = assumptions["washer_thickness_mm"]
    screw_length = assumptions["board_screw_under_head_length_mm"]
    head_height = assumptions["board_screw_head_height_mm"]
    boss_thickness = assumptions["mount_boss_thickness_mm"]
    tap_depth = assumptions["mount_boss_tap_depth_mm"]
    foot_thickness = assumptions["frame_foot_thickness_mm"]
    dimensions = (spacer_height, washer_thickness, screw_length, head_height,
                  boss_thickness, tap_depth, foot_thickness)
    if not all(math.isfinite(value) and value > 0 for value in dimensions):
        raise ValueError("Holder nominal dimensions must be finite and positive")
    if tap_depth >= min(boss_thickness, foot_thickness):
        raise ValueError("Blind receiving holes must retain a nominal bottom wall")
    frame_grip = FRAME_OUTER-FRAME_INNER
    frame_engagement = 10-frame_grip
    if not 0 < frame_engagement < tap_depth:
        raise ValueError("The nominal frame screw has no engagement or bottoms out")
    shapes, joints, details = {}, [], {}
    for kind in ("pcb", "mpu"):
        spec = conditions[kind]
        label = kind.upper()
        holder_id, board_id = "E_HOLDER_"+label, "E_REF_BOARD_"+label
        distance = spec["source_holder_plane_from_origin_mm"]
        transverse = spec["frame_attachment_transverse_mm"]
        if kind == "pcb":
            datum = spec["hole_datum_board_xy_mm"]
            holes = [(x-datum[0], y-datum[1]) for x,y in spec["mounting_holes_board_xy_mm"]]
            width, height = spec["mechanical_outline_bbox_size_mm"]
            board_thickness = spec["nominal_board_thickness_mm"]
            hole_radius = spec["mounting_hole_diameter_mm"]/2
            origin_uv = (-datum[0], -datum[1])
            nodes = [on_plane(u, v, distance-2) for u,v in holes]
            stock = rib(nodes[0], nodes[1])
            for i in range(1, len(nodes)):
                stock = stock.fuse(rib(nodes[i], nodes[(i+1) % len(nodes)]))
        else:
            holes = [tuple(row) for row in spec["source_holder_hole_uv_mm"]]
            width, height, _ = spec["nominal_board_envelope_mm"]
            board_thickness = spec["nominal_board_envelope_mm"][2]
            hole_radius = spec["nominal_mounting_hole_diameter_mm"]/2
            origin_uv = (-width/2, -height/2)
            stock = plane_box(24, 20, 4, -12, -10, distance-4)
            nodes = [on_plane(8,-6,distance-2), on_plane(0,8,distance-2), on_plane(-8,-6,distance-2)]
        if not math.isfinite(board_thickness) or board_thickness <= 0 or not math.isfinite(hole_radius) or hole_radius <= 1.5:
            raise ValueError("Board thickness and nominal screw clearance are invalid")
        grip = spacer_height+board_thickness+washer_thickness
        engagement = screw_length-grip
        if not 0 < engagement < tap_depth:
            raise ValueError("The nominal board screw has no engagement or bottoms out")
        for u,v in holes:
            stock = stock.fuse(Part.makeCylinder(3.5, boss_thickness, on_plane(u,v,distance-boss_thickness), N))
        for axis, axis_name in enumerate("XYZ"):
            low, dimensions = [transverse-4]*3, [8.0]*3
            low[axis], dimensions[axis] = FRAME_INNER-foot_thickness, foot_thickness
            foot = Part.makeBox(*dimensions, App.Vector(*low))
            root = [transverse]*3; root[axis] = FRAME_INNER-foot_thickness+.5
            start = App.Vector(*root)
            target = min(nodes, key=lambda p: (p-start).Length) if kind == "pcb" else nodes[axis]
            direction = target-start
            beam = Part.makeCylinder(3, direction.Length, start, direction)
            stock = stock.fuse(foot).fuse(beam)
            seat = [transverse]*3; seat[axis] = FRAME_OUTER
            inward = axis_vector(axis,-1)
            screw_id = "E_HOLDER_FIX_"+label+"_"+axis_name
            screw = Part.makeCylinder(1.5,10,App.Vector(*seat),inward).fuse(Part.makeCone(3,1.5,1.7,App.Vector(*seat),inward))
            shapes[screw_id] = screw.removeSplitter()
            joints.append({"id":"EH_FRAME_"+label+"_"+axis_name,"fastener":screw_id,
                "clamped_part":"E_FRAME_BOARD_"+axis_name,"receiver":holder_id,
                "axis":list(inward),"seat_point_mm":seat,"frame_grip_mm":frame_grip,
                "engagement_mm":frame_engagement,"tap_depth_mm":tap_depth,"bottom_margin_mm":tap_depth-frame_engagement,
                "thread_major_radius_mm":1.5,"thread_minor_radius_mm":1.25,
                "nominal_length_mm":10,"length_convention":"including-head","modeled_total_length_mm":10,
                "nominal_thread":"M3x0.5","seat_kind":"flat-head D6/h1.7","tightening_torque_Nm":None,"physical_ready":False})
        stock = stock.cut(plane_box(200, 200, 100, -100, -100, distance))
        # All stock and the flat board seat are formed before receiving holes.
        for axis in range(3):
            p = [transverse]*3; p[axis] = FRAME_INNER+.0001
            stock = stock.cut(Part.makeCylinder(1.25,tap_depth+.0001,App.Vector(*p),axis_vector(axis,-1)))
        for u,v in holes:
            stock = stock.cut(Part.makeCylinder(1.25,tap_depth+.0001,on_plane(u,v,distance+.0001),-N))
        shapes[holder_id] = stock.removeSplitter()
        board = plane_box(width,height,board_thickness,*origin_uv,distance+spacer_height)
        for i,(u,v) in enumerate(holes):
            board = board.cut(Part.makeCylinder(hole_radius,board_thickness+.002,
                                              on_plane(u,v,distance+spacer_height-.001),N))
            spacer_id, washer_id = f"E_SPACER_{label}_{i}", f"E_WASHER_{label}_{i}"
            screw_id = f"E_BOARD_SCREW_{label}_{i}"
            shapes[spacer_id] = tube(3,1.7,spacer_height,on_plane(u,v,distance))
            shapes[washer_id] = tube(3.5,1.7,washer_thickness,on_plane(u,v,distance+spacer_height+board_thickness))
            seat = on_plane(u,v,distance+grip)
            shapes[screw_id] = Part.makeCylinder(1.5,screw_length,seat,-N).fuse(
                Part.makeCylinder(2.75,head_height,seat,N)).removeSplitter()
            joints.append({"id":f"EH_BOARD_{label}_{i}","fastener":screw_id,
                "clamped_part":washer_id,"receiver":holder_id,
                "stack":[washer_id,board_id,spacer_id,holder_id],
                "axis":list(-N),"seat_point_mm":list(seat),"frame_grip_mm":grip,
                "engagement_mm":engagement,"tap_depth_mm":tap_depth,"bottom_margin_mm":tap_depth-engagement,
                "thread_major_radius_mm":1.5,"thread_minor_radius_mm":1.25,
                "nominal_length_mm":screw_length,"length_convention":"under-head",
                "head_height_mm":head_height,"modeled_total_length_mm":screw_length+head_height,
                "nominal_thread":"M3x0.5",
                "seat_kind":"flat underside of D5.5 head on washer","tightening_torque_Nm":None,
                "physical_ready":False,"actual_board_fit_qualified":False})
        shapes[board_id] = board.removeSplitter()
        details[holder_id] = {"reference_board":board_id,"holes_uv_mm":holes,"plane_mm":distance,
            "frame_attachment_transverse_mm":transverse,"new_nominal_spacer_mm":spacer_height,
            "nominal_board_thickness_mm":board_thickness,"washer_thickness_mm":washer_thickness,
            "board_hole_diameter_mm":hole_radius*2,
            "hole_diameter_basis":"Pico mechanical drill data" if kind == "pcb" else "new nominal assumption; actual MPU holes unverified",
            "source_geometry_read":False,"actual_electrical_fit_qualified":False}
    return shapes, joints, details
