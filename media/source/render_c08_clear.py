"""One large view per cause: marked rotation, separate schematic pull, friction stop."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import time

import bpy
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import render_c08 as original
from clarity_timeline import make_timeline

DATA = original.DATA
TIMELINE = make_timeline()
S = .01
W, H = 1280, 576


def material(name, color, metal=0.0):
    value = original.mat(name, color, metal)
    shader = value.node_tree.nodes["Principled BSDF"]
    shader.inputs["Roughness"].default_value = .52
    shader.inputs["Specular IOR Level"].default_value = .12
    return value


def marked_material(name, color, opacity=1):
    value = material(name, color, .18)
    nodes, links = value.node_tree.nodes, value.node_tree.links
    tex = nodes.new("ShaderNodeTexCoord")
    xyz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(tex.outputs["Generated"], xyz.inputs[0])

    def operation(op, *values):
        n = nodes.new("ShaderNodeMath")
        n.operation = op
        for i, v in enumerate(values):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                links.new(v, n.inputs[i])
        return n.outputs[0]

    x = operation("SUBTRACT", xyz.outputs["X"], .5)
    y = operation("SUBTRACT", xyz.outputs["Y"], .5)
    angle = operation("ARCTAN2", y, x)
    radius = operation("SQRT", operation("ADD", operation("MULTIPLY", x, x), operation("MULTIPLY", y, y)))
    long_mark = operation("MULTIPLY", operation("GREATER_THAN", angle, .10), operation("LESS_THAN", angle, .35))
    short_mark = operation("MULTIPLY", operation("GREATER_THAN", angle, -2.30), operation("LESS_THAN", angle, -2.15))
    mark = operation("MULTIPLY", operation("GREATER_THAN", radius, .29),
                     operation("MINIMUM", 1, operation("ADD", long_mark, short_mark)))
    mix = nodes.new("ShaderNodeMixRGB")
    mix.inputs[1].default_value = (*color, 1)
    mix.inputs[2].default_value = (.98, .98, .98, 1)
    links.new(mark, mix.inputs[0])
    links.new(mix.outputs[0], nodes["Principled BSDF"].inputs["Base Color"])
    if opacity < 1:
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        factor = nodes.new("ShaderNodeMath")
        factor.operation = "MAXIMUM"
        factor.inputs[1].default_value = opacity
        links.new(mark, factor.inputs[0])
        blend = nodes.new("ShaderNodeMixShader")
        links.new(factor.outputs[0], blend.inputs[0])
        links.new(transparent.outputs[0], blend.inputs[1])
        links.new(nodes["Principled BSDF"].outputs[0], blend.inputs[2])
        links.new(blend.outputs[0], nodes["Material Output"].inputs[0])
    return value


def cube(scene, name, center, size, mat):
    x, y, z = center
    dx, dy, dz = (v / 2 for v in size)
    verts = [(x + a * dx, y + b * dy, z + c * dz) for a, b, c in
             [(-1,-1,-1), (1,-1,-1), (1,1,-1), (-1,1,-1),
              (-1,-1,1), (1,-1,1), (1,1,1), (-1,1,1)]]
    faces = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    mesh.materials.append(mat)
    bevel = obj.modifiers.new("Illustration edge", "BEVEL")
    bevel.width, bevel.segments = .01, 2
    return obj


def ribbon(scene, name, mat):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = .028
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(30)
    obj = bpy.data.objects.new(name, curve)
    scene.collection.objects.link(obj)
    curve.materials.append(mat)
    return obj


def arrow_curve(scene, mat):
    curve = bpy.data.curves.new("Friction opposite rotation", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth, curve.bevel_resolution = .013, 3
    points = []
    for i in range(49):
        a = math.radians(200 - i * 1.8)
        points.append((.68 * math.cos(a), .68 * math.sin(a), -.692, 1))
    spline = curve.splines.new("POLY")
    spline.points.add(len(points)-1)
    for v, co in zip(spline.points, points):
        v.co = co
    obj = bpy.data.objects.new(curve.name, curve)
    scene.collection.objects.link(obj)
    curve.materials.append(mat)
    end = Vector(points[-1][:3])
    a = math.radians(200-48*1.8)
    tangent = Vector((math.sin(a), -math.cos(a), 0))
    radial = Vector((math.cos(a), math.sin(a), 0))
    vertices = [tuple(end + tangent * .055),
                tuple(end - tangent * .015 + radial * .042),
                tuple(end - tangent * .015 - radial * .042)]
    mesh = bpy.data.meshes.new("Friction direction arrowhead")
    mesh.from_pydata(vertices, [], [(0,1,2),(2,1,0)])
    mesh.update()
    head = bpy.data.objects.new(mesh.name, mesh)
    scene.collection.objects.link(head)
    mesh.materials.append(mat)
    return [obj, head]


def make_scene(name):
    scene = original.scene(name, W, H)
    scene.frame_end = 960
    scene.eevee.taa_render_samples = 24
    scene.view_settings.exposure = -.65
    return scene


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = {
        "fixed": material("Gray fixed parts", (.32,.36,.42), .35),
        "rotating": material("Blue rotating attachments", (.055,.30,.67), .25),
        "copper": material("Orange stationary electromagnet", (.70,.20,.025), .2),
        "lining": material("Gray stationary friction face", (.15,.18,.22), 0),
        "armature": marked_material("Light blue movable disc white marks", (.08,.48,.81)),
        "spring": material("Spring explanatory green", (.39,.66,.24), .15),
        "hub": material("Blue hub", (.045,.22,.54), .28),
        "wheel": marked_material("Blue reference wheel white radial marks", (.06,.30,.68)),
        "wheel_transparent": marked_material("Reference wheel transparent with clear white phase marks", (.06,.30,.68), .25),
        "reference": material("Reference motor gray", (.25,.28,.32), .4),
        "peek": material("Bobbin neutral", (.47,.44,.38)),
        "frame": material("Frame reference", (.30,.35,.40), .3),
        "stripe": material("White phase mark", (.95,.97,1)),
    }
    scenes = {name: make_scene(name) for name in ("Overview", "Mechanism", "Schematic")}
    objects = {key: [] for key in scenes}
    overview, main, diagram = [scenes[n] for n in ("Overview", "Mechanism", "Schematic")]
    for axis in ("X","Y","Z"):
        for part in DATA["parts"]:
            if part["id"] == "REF_FRAME" or part["id"].startswith("BEARING_BALL_"):
                continue
            obj = original.object_mesh(overview, part, mats, axis+"_")
            q = DATA["axis_quaternions_xyzw"][axis]
            obj.matrix_world = Quaternion((q[3],q[0],q[1],q[2])).to_matrix().to_4x4()
            objects["Overview"].append(obj)
    for part in DATA["enclosure_frames"]:
        p = {**part, "motion_group":"fixed", "material_code":"reference", "is_reference":True}
        obj = original.object_mesh(overview, p, mats)
        obj.data.materials.clear()
        obj.data.materials.append(mats["frame"])
    for part in DATA["parts"]:
        if part["id"] == "REF_FRAME" or part["id"].startswith("BEARING_BALL_"):
            continue
        if part["motion_group"] == "fixed" and part["id"] != "WINDING":
            if "cutaway" not in part:
                continue
            cutaway = part["cutaway"]
        else:
            cutaway = None
        obj = original.object_mesh(main, part, mats, override=cutaway)
        if part["id"] == "REF_WHEEL":
            obj.data.materials.clear()
            obj.data.materials.append(mats["wheel_transparent"])
        objects["Mechanism"].append(obj)
    # A separate explanatory drawing in3D: no source fabrication shape is altered.
    schem = {}
    schem["hub"] = cube(diagram,"Schematic hub fixed axial position",(-.93,.05,.12),(1.16,.25,.18),mats["hub"])
    schem["disc"] = cube(diagram,"Schematic thin movable disc",(.07,0,.65),(.10,.24,1.05),mats["armature"])
    schem["disc"].data.materials.clear()
    schem["disc"].data.materials.append(material("Schematic blue disc",(.07,.40,.78),.15))
    schem["face"] = cube(diagram,"Schematic fixed friction face",(.52,0,.70),(.08,.29,.90),mats["lining"])
    schem["coil"] = cube(diagram,"Schematic orange stationary coil",(.94,.07,.70),(.62,.22,.65),mats["copper"])
    cube(diagram,"Schematic yoke back",(1.34,.03,.69),(.14,.30,1.12),mats["fixed"])
    cube(diagram,"Schematic yoke top",(.95,.03,1.20),(.91,.30,.14),mats["fixed"])
    cube(diagram,"Schematic yoke foot",(.96,.03,.19),(.90,.30,.14),mats["fixed"])
    schem["spring"] = ribbon(diagram,"Schematic spring root stays at hub",mats["spring"])
    schem["contact"] = cube(diagram,"Contact highlight only",(.482,-.17,.70),(.035,.025,.85),
                            material("Contact yellow indicator",(1,.73,.08)))
    indicator = material("Braking force directional indicator",(.95,.23,.14))
    forces = arrow_curve(main,indicator)
    original.camera(overview,(-3.1,-3.7,-3.0),(0,0,0),4.9)
    original.camera(main,(1.05,-1.60,-1.76),(0,0,-.58),2.22)
    original.camera(diagram,(0,-5,.65),(0,0,.65),3.75)
    for scene in scenes.values():
        for light in (o for o in scene.objects if o.type == "LIGHT"):
            light.data.energy *= .75
    return scenes, objects, schem, mats, forces


def update(scenes, objects, schem, mats, forces, frame, bake=False):
    n = frame["frame"]
    for scene in scenes.values():
        scene.frame_set(n)
    for obj in objects["Mechanism"]:
        group = obj["motion_group"]
        matrix = Matrix.Identity(4)
        if group in ("rotate_only","rotate_and_axial","rotating_spring"):
            matrix = Matrix.Rotation(math.radians(frame["rotor_angle_deg"]),4,"Z")
        if group == "rotate_and_axial":
            matrix = Matrix.Translation(Vector((0,0,frame["armature_axial_mm"]*S))) @ matrix
        obj.matrix_world = matrix
        if obj.data.shape_keys:
            k = obj.data.shape_keys.key_blocks["Axial_flex_explanation"]
            k.value = frame["armature_axial_mm"]/.2
            if bake:
                k.keyframe_insert("value",frame=n)
        if bake and group in ("rotate_only","rotate_and_axial","rotating_spring"):
            obj.keyframe_insert("location",frame=n)
            obj.keyframe_insert("rotation_euler",frame=n)
    displacement = .36 * frame["armature_axial_mm"]/.2
    schem["disc"].location.x = displacement
    for i, p in enumerate(schem["spring"].data.splines[0].points):
        u = i/30
        weight = u*u*(3-2*u)
        p.co = (-.69 + (.76)*u + displacement*weight, -.02, .20 + .46*u, 1)
        if bake:
            p.keyframe_insert("co",frame=n)
    schem["contact"].hide_render = not frame["contact"]
    for arrow in forces:
        arrow.hide_render = not frame["friction_arrow"]
        if bake:
            arrow.keyframe_insert("hide_render",frame=n)
    if bake:
        schem["disc"].keyframe_insert("location",frame=n)
        schem["contact"].keyframe_insert("hide_render",frame=n)
    shader = mats["copper"].node_tree.nodes["Principled BSDF"].inputs["Base Color"]
    shader.default_value = (.94,.30,.025,1) if frame["coil_on"] else (.55,.13,.018,1)
    if bake:
        shader.keyframe_insert("default_value",frame=n)


def projected(scene, point):
    local = scene.camera.rotation_euler.to_matrix().transposed() @ (Vector(point)-scene.camera.location)
    width=scene.camera.data.ortho_scale
    height=width*H/W
    return [round((.5+local.x/width)*W,2), round(104+(.5-local.y/height)*H,2)]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--all",action="store_true")
    parser.add_argument("--frames",default="145,385,529,601,721,865")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    (ROOT/"clarity-timeline.json").write_text(json.dumps(TIMELINE,ensure_ascii=False,indent=2)+"\n")
    scenes,objects,schem,mats,forces=setup()
    (ROOT/"clarity-label-points.json").write_text(json.dumps({
        "actual":{name:projected(scenes["Mechanism"],p) for name,p in {
            "wheel":(-.46,-.26,-.68),"armature":(.32,-.24,-.618),
            "magnet":(.30,.18,-.54),"fixed":(.54,.10,-.49),"hub":(.0,0,-.667)
        }.items()},
        "schematic":{name:projected(scenes["Schematic"],p) for name,p in {
            "disc":(.07,0,.90),"face":(.52,0,1.02),"coil":(.94,0,.8),"hub":(-.94,0,.14),
            "spring":(-.38,-.05,.35),"gap_start":(.14,-.20,.88),"gap_end":(.46,-.20,.88)
        }.items()},
    },indent=2)+"\n")
    out=ROOT/"clarity-frames";out.mkdir(exist_ok=True)
    selected=range(1,961) if args.all else [int(n) for n in args.frames.split(",")]
    cache={}
    start=time.monotonic()
    for number in selected:
        frame=TIMELINE["frames"][number-1]
        update(scenes,objects,schem,mats,forces,frame)
        scene=scenes[frame["view"]]
        target=out/f"{number:04d}.png"
        if frame["view"]=="Overview":
            key=("Overview",)
        elif frame["view"]=="Mechanism":
            key=("Mechanism",round(frame["rotor_angle_deg"],9),round(frame["armature_axial_mm"],9),frame["coil_on"],frame["friction_arrow"])
        else:
            key=("Schematic",round(frame["armature_axial_mm"],9),frame["coil_on"],frame["contact"])
        if key in cache:
            shutil.copyfile(cache[key],target)
        else:
            scene.render.filepath=str(target)
            bpy.ops.render.render(write_still=True,scene=scene.name)
            cache[key]=target
        print(json.dumps({"frame":number,"view":frame["view"],"stage":frame["stage"],"seconds":round(time.monotonic()-start,1)}),flush=True)
    for frame in TIMELINE["frames"]:
        update(scenes,objects,schem,mats,forces,frame,bake=True)
    update(scenes,objects,schem,mats,forces,TIMELINE["frames"][0])
    bpy.context.window.scene=scenes["Mechanism"]
    for scene in scenes.values():
        scene.render.filepath="//clarity-frames/"
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"c08-clear-animation.blend"),compress=True)


if __name__=="__main__":
    main()
