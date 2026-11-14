"""C08 source-matched explanatory animation. No manufacturing geometry is written."""
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
DATA = json.loads((ROOT / "c08-scene-data.json").read_text())
S = .01


def mat(name, color, metal=0, alpha=1):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    shader = m.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metal
    shader.inputs["Roughness"].default_value = .45
    shader.inputs["Specular IOR Level"].default_value = .22
    if alpha < 1:
        nodes, links = m.node_tree.nodes, m.node_tree.links
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = alpha
        links.new(transparent.outputs[0], mix.inputs[1])
        links.new(shader.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], nodes.get("Material Output").inputs[0])
    return m


def material_for(p, mats, kind):
    name = p["id"]
    if name == "WINDING":
        return mats["copper"]
    if name.startswith("LINING_") and not name.startswith("LINING_KEEPER"):
        return mats["lining"]
    if name == "ARMATURE":
        return mats["armature"]
    if name.startswith("SPRING_") and name[len("SPRING_"):].isdigit():
        return mats["spring"]
    if name in ("HUB", "HUB_FACE"):
        return mats["hub"]
    if name in ("REF_WHEEL",):
        return mats["wheel_transparent"] if kind == "Single" else mats["wheel"]
    if name.startswith("REF_"):
        return mats["reference"]
    if p["material_code"] in ("PEEK",):
        return mats["peek"]
    return mats["fixed"] if p["motion_group"] in ("fixed", "fixed_reference") else mats["rotating"]


def scene(name, width, height):
    s = bpy.data.scenes.new(name)
    s.render.engine = "BLENDER_EEVEE"
    s.render.resolution_x, s.render.resolution_y = width, height
    s.render.resolution_percentage = 100
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGB"
    s.render.fps = 24
    s.frame_start, s.frame_end = 1, 528
    s.render.threads_mode = "FIXED"
    s.render.threads = 6
    s.eevee.taa_render_samples = 32 if name in ("Overview", "Single") else 12
    s.world = bpy.data.worlds.new(name + " world")
    s.world.use_nodes = True
    s.world.node_tree.nodes["Background"].inputs[0].default_value = (.045,.085,.13,1)
    s.world.node_tree.nodes["Background"].inputs[1].default_value = .45
    s.view_settings.view_transform = "AgX"
    s.view_settings.exposure = -.2
    camera = bpy.data.objects.new(name + " Camera", bpy.data.cameras.new(name + " camera"))
    camera.data.type = "ORTHO"
    camera.data.clip_start, camera.data.clip_end = .001, 100
    s.collection.objects.link(camera)
    s.camera = camera
    for i, (pos, power, size) in enumerate([((-3,-4,-4),800,4),((3,-2,3),650,3),((0,4,-1),650,4)]):
        data = bpy.data.lights.new(name + str(i), "AREA")
        data.energy, data.shape, data.size = power, "DISK", size
        o=bpy.data.objects.new(data.name,data);s.collection.objects.link(o);o.location=pos
        o.rotation_euler=(Vector((0,0,-.5))-o.location).to_track_quat("-Z","Y").to_euler()
    return s


def camera(s, pos, target, ortho, up="Y"):
    o=s.camera;o.location=pos
    q=(Vector(target)-o.location).to_track_quat("-Z","Y")
    if up=="radial":
        q=q@Quaternion(Vector((0,0,1)),math.pi/2)
    o.rotation_euler=q.to_euler()
    o.data.ortho_scale=ortho


def object_mesh(s, p, mats, prefix="", override=None):
    geo=override or p
    name=prefix+p["id"]
    data=bpy.data.meshes.new(s.name+" "+name)
    data.from_pydata([[v*S for v in vertex] for vertex in geo["vertices"]],[],geo["faces"])
    data.update()
    obj=bpy.data.objects.new(data.name,data);s.collection.objects.link(obj)
    data.materials.append(material_for(p,mats,s.name))
    obj["part_id"]=p["id"];obj["motion_group"]=p["motion_group"];obj["axis"]=prefix[:1] if prefix else "Z"
    if "axial_weights" in p and override is None:
        obj.shape_key_add(name="Reference")
        moved=obj.shape_key_add(name="Axial_flex_explanation")
        for i,w in enumerate(p["axial_weights"]):
            moved.data[i].co.z+=.2*S*w
    return obj


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats={
        "fixed":mat("Fixed yoke poles carrier",(.30,.36,.46),.62),
        "rotating":mat("Rotating fasteners",(.40,.48,.57),.62),
        "copper":mat("Ring winding - state color only",(.62,.19,.035),.5),
        "lining":mat("Fixed friction lining",(.32,.11,.055),0),
        "armature":mat("Axially movable armature",(.10,.60,.62),.6),
        "spring":mat("Tangential leaf springs",(.62,.80,.18),.35),
        "hub":mat("Axially retained rotating hub",(.12,.30,.63),.65),
        "wheel":mat("Independent reference wheel",(.18,.43,.68),.5),
        "wheel_transparent":mat("Reference wheel shown transparent",(.18,.43,.68),.4,.20),
        "reference":mat("Independent reference motor",(.19,.23,.29),.4),
        "peek":mat("Insulating bobbin",(.73,.62,.37),0),
        "frame":mat("Independent138mm frame",(.25,.35,.47),.6),
        "stripe":mat("Rotation phase marker - explanation",(.97,.66,.10),0),
    }
    overview=scene("Overview",848,504);single=scene("Single",848,504)
    section=scene("Section",400,246);spring=scene("Spring",400,226)
    scenes=[overview,single,section,spring]
    objects={s.name:[] for s in scenes}
    for axis in ("X","Y","Z"):
        for p in DATA["parts"]:
            if p["id"]=="REF_FRAME" or p["id"].startswith("BEARING_BALL_"):continue
            o=object_mesh(overview,p,mats,axis+"_")
            q=DATA["axis_quaternions_xyzw"][axis]
            o.matrix_world=Quaternion((q[3],q[0],q[1],q[2])).to_matrix().to_4x4()
            objects["Overview"].append(o)
    for p in DATA["enclosure_frames"]:
        pp={**p,"motion_group":"fixed","material_code":"reference","is_reference":True}
        o=object_mesh(overview,pp,mats)
        o.data.materials.clear();o.data.materials.append(mats["frame"])
    for p in DATA["parts"]:
        if p["id"]=="REF_FRAME" or p["id"].startswith("BEARING_BALL_"):continue
        if p["motion_group"]=="fixed" and p["id"]!="WINDING":
            if "cutaway" not in p:continue
            override=p["cutaway"]
        else:override=None
        objects["Single"].append(object_mesh(single,p,mats,override=override))
        if p["id"] in ("SPRING_0","SPRING_CLAMP_ROOT_0","SPRING_CLAMP_TIP_0",
                       "SPRING_ROOT_NUT_PLATE_0","SPRING_TIP_NUT_PLATE_0",
                       "SPRING_ROOT_BOLT_0","SPRING_ROOT_BOLT_1","SPRING_TIP_BOLT_0","SPRING_TIP_BOLT_1"):
            objects["Spring"].append(object_mesh(spring,p,mats))
    for p in DATA["axial_section"]:
        objects["Section"].append(object_mesh(section,p,mats))
    camera(overview,(-3.1,-3.7,-3.0),(0,0,0),4.25)
    camera(single,(1.1,-2.0,-.10),(0,.08,-.57),1.85)
    camera(section,(-.8,.36,-.621),(0,.36,-.621),.106,up="radial")
    # Side view of the source tangential spring; camera moves with rotor in the main view.
    camera(spring,(1.0,.18,-.77),(.24,.18,-.645),.48)
    return scenes,objects,mats


def update(scenes,objects,mats,state,bake=False):
    for s in scenes:
        s.frame_set(state["frame"])
        for o in objects[s.name]:
            group=o["motion_group"]
            angle=state["angle_deg"] if s.name=="Single" else 0
            m=Matrix.Identity(4)
            if group in ("rotate_only","rotate_and_axial","rotating_spring"):
                m=Matrix.Rotation(math.radians(angle),4,"Z")
            if group=="rotate_and_axial":
                m=Matrix.Translation(Vector((0,0,state["axial_mm"]*S)))@m
            if s.name=="Overview":
                q=DATA["axis_quaternions_xyzw"][o["axis"]]
                m=Quaternion((q[3],q[0],q[1],q[2])).to_matrix().to_4x4()
            o.matrix_world=m
            if o.data.shape_keys:
                key=o.data.shape_keys.key_blocks["Axial_flex_explanation"]
                key.value=state["axial_mm"]/.2
                if bake:key.keyframe_insert("value",frame=state["frame"])
            if bake and s.name!="Overview" and group in ("rotate_only","rotate_and_axial","rotating_spring"):
                o.keyframe_insert("location",frame=state["frame"])
                o.keyframe_insert("rotation_euler",frame=state["frame"])
    color=(.98,.35,.06,1) if state["coil_on"] else (.62,.19,.035,1)
    socket=mats["copper"].node_tree.nodes["Principled BSDF"].inputs["Base Color"]
    socket.default_value=color
    if bake:socket.keyframe_insert("default_value",frame=state["frame"])


def main():
    args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    p=argparse.ArgumentParser();p.add_argument("--all",action="store_true");p.add_argument("--frames",default="1,241,337,397,505")
    cfg=p.parse_args(args)
    scenes,objects,mats=setup()
    output=ROOT/"c08-frames";output.mkdir(exist_ok=True)
    wanted=range(1,529) if cfg.all else [int(n) for n in cfg.frames.split(",")]
    cache={};start=time.monotonic()
    for f in wanted:
        state=DATA["frames"][f-1];update(scenes,objects,mats,state)
        for s in scenes:
            folder=output/s.name.lower();folder.mkdir(exist_ok=True);target=folder/f"{f:04d}.png"
            key=(s.name,round(state["axial_mm"],9),state["coil_on"])
            if s.name=="Overview":key=("Overview",)
            elif s.name=="Single":key=(s.name,round(state["angle_deg"],9),round(state["axial_mm"],9),state["coil_on"])
            if key in cache:shutil.copyfile(cache[key],target)
            else:
                s.render.filepath=str(target);bpy.ops.render.render(write_still=True,scene=s.name);cache[key]=target
        print(json.dumps({"frame":f,"stage":state["stage"],"elapsed_s":round(time.monotonic()-start,1)}),flush=True)
    for state in DATA["frames"]:update(scenes,objects,mats,state,bake=True)
    update(scenes,objects,mats,DATA["frames"][0])
    bpy.context.window.scene=scenes[1]
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"c08-coaxial-animation.blend"),compress=True)
    s=scenes[0]
    bpy.context.window.scene=s
    bpy.context.view_layer.update()
    labels={}
    for name,p in (("X",(-65,0,0)),("Y",(0,-65,0)),("Z",(0,0,-65))):
        local=s.camera.rotation_euler.to_matrix().transposed()@(Vector(p)*S-s.camera.location)
        w=s.camera.data.ortho_scale
        h=w*504/848
        labels[name]=[8+(local.x/w+.5)*848,128+(.5-local.y/h)*504]
    (ROOT/"c08-axis-labels.json").write_text(json.dumps(labels,indent=2)+"\n")


if __name__=="__main__":main()
