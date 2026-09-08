"""Build and export the editable studio. Run through Blender's Python runtime."""

import argparse
import json
import math
import struct
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0,str(HERE))

from common import Studio, WIDTH, HEIGHT
from architecture import build_architecture, fuse_architecture
from observatory import build_observatory
from interiors import build_interiors
from tree import build_tree
from motion import build_motion

MOTION_PREFIXES = ("Steam", "FallingPetal", "ScreenGlow")


def projection():
    objects=[]
    triangles=[]
    owners=[]
    face_ids=[]
    for obj in bpy.context.scene.objects:
        if obj.type!="MESH" or obj.name.startswith(MOTION_PREFIXES):
            continue
        mesh=obj.data
        mesh.calc_loop_triangles()
        vertices=np.array([(v.x,HEIGHT-v.z,v.y) for v in (obj.matrix_world @ vertex.co for vertex in mesh.vertices)],dtype=np.float32)
        source=not obj.name.startswith("Setting")
        groups=json.loads(obj.get("surfaceGroups","{}"))
        if not groups:
            groups={"": {"faces": list(range(len(mesh.polygons))), "fill":obj.get("sourceFill","blue")}}
        assignments={}
        for label,group in groups.items():
            if not group["faces"]:
                continue
            face_set=set(group["faces"])
            selected=[triangle for triangle in mesh.loop_triangles if triangle.polygon_index in face_set]
            if not selected:
                continue
            bounds_vertices=vertices[list({index for tri in selected for index in tri.vertices})]
            index=len(objects)
            objects.append({"name":obj.name+("::"+label if label else ""),"object":obj.name,"faces":group["faces"],"source":source,"fill":group["fill"],"bounds":[float(bounds_vertices[:,0].min()),float(bounds_vertices[:,1].min()),float(bounds_vertices[:,0].max()),float(bounds_vertices[:,1].max())]})
            for face in face_set:
                assignments[face]=index
        for triangle in mesh.loop_triangles:
            if triangle.polygon_index not in assignments:
                raise RuntimeError(f"Unassigned surface: {obj.name} face {triangle.polygon_index}")
            triangles.append(vertices[list(triangle.vertices)])
            owners.append(assignments[triangle.polygon_index])
            face_ids.append(triangle.polygon_index)
    folder=ROOT/"assets/studio"
    np.savez_compressed(folder/"projection.npz",triangles=np.array(triangles,dtype=np.float32),owners=np.array(owners,dtype=np.int32),face_ids=np.array(face_ids,dtype=np.int32))
    (folder/"projection.json").write_text(json.dumps(objects,ensure_ascii=False)+"\n")
    print(f"PROJECTED {len(objects)} objects / {len(triangles)} triangles",flush=True)


def camera():
    data=bpy.data.cameras.new("ReferenceCamera")
    obj=bpy.data.objects.new("ReferenceCamera",data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location=(768,-3000,512)
    obj.rotation_euler=(Vector((768,0,512))-obj.location).to_track_quat("-Z","Y").to_euler()
    data.type="ORTHO"
    data.ortho_scale=1536
    data.clip_start=.1
    data.clip_end=10000
    bpy.context.scene.camera=obj
    bpy.context.scene.render.resolution_x=WIDTH
    bpy.context.scene.render.resolution_y=HEIGHT
    bpy.context.scene.render.resolution_percentage=100


def apply_atlas(api):
    spec=json.loads((ROOT/"assets/studio/atlas.json").read_text())
    materials={}
    for key,info in spec["objects"].items():
        obj=bpy.data.objects.get(info.get("object",key))
        if obj is None or obj.type!="MESH":
            raise RuntimeError(f"Missing atlas target {key}")
        mesh=obj.data
        uv=mesh.uv_layers.active
        fill=info.get("fill",obj.get("sourceFill","blue"))
        fill_index=len(mesh.materials)
        mesh.materials.append(api.material(fill))
        atlas_index=None
        if "page" in info:
            page=info["page"]
            if page not in materials:
                materials[page]=api.material(f"atlas-{page}")
            atlas_index=len(mesh.materials)
            mesh.materials.append(materials[page])
        visible_faces=set(info.get("visibleFaces",[]))
        for index in info.get("faces",range(len(mesh.polygons))):
            polygon=mesh.polygons[index]
            visible=index in visible_faces
            polygon.material_index=atlas_index if visible else fill_index
            for loop in polygon.loop_indices:
                position=obj.matrix_world @ mesh.vertices[mesh.loops[loop].vertex_index].co
                image_x,image_y=position.x,HEIGHT-position.z
                if visible:
                    x0,y0,_,_=info["bounds"]
                    offset_x,offset_y=info["origin"]
                    uv.data[loop].uv=((offset_x+image_x-x0)/spec["size"],1-(offset_y+image_y-y0)/spec["size"])
                else:
                    uv.data[loop].uv=(image_x/110,image_y/110)


def batch_static():
    """Only the exported copy is joined; the saved Blender objects stay editable."""
    groups={}
    for obj in bpy.context.scene.objects:
        if obj.type=="MESH" and not obj.name.startswith(MOTION_PREFIXES):
            key=obj.name.split(".")[0].split("_")[0]
            if key.startswith("Bonsai"):
                key="Bonsai"
            elif key.startswith("Setting"):
                key="Setting"
            elif key.startswith("Observatory"):
                key="Observatory"
            else:
                key="Studio"
            groups.setdefault(key,[]).append(obj)
    for name,objects in groups.items():
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active=objects[0]
        bpy.ops.object.join()
        objects[0].name=name+"_Static"


def normalize_unlit(path):
    """Export emission-only paint as the standard glTF unlit material model."""
    data=path.read_bytes()
    json_length,json_type=struct.unpack_from("<II",data,12)
    assert json_type==0x4E4F534A
    document=json.loads(data[20:20+json_length])
    for material in document.get("materials",[]):
        pbr=material.setdefault("pbrMetallicRoughness",{})
        alpha=pbr.get("baseColorFactor",[0,0,0,1])[3]
        if "emissiveTexture" in material:
            pbr["baseColorTexture"]=material.pop("emissiveTexture")
            pbr["baseColorFactor"]=[1,1,1,alpha]
        else:
            pbr["baseColorFactor"]=[*material.get("emissiveFactor",[1,1,1]),alpha]
        material.pop("emissiveFactor",None)
        material.setdefault("extensions",{})["KHR_materials_unlit"]={}
        if "cutout" in material.get("name",""):
            material["alphaMode"]="MASK"
            material["alphaCutoff"]=.5
            material["doubleSided"]=True
    used=document.setdefault("extensionsUsed",[])
    if "KHR_materials_unlit" not in used:
        used.append("KHR_materials_unlit")
    encoded=json.dumps(document,separators=(",",":")).encode()
    encoded+=b" "*((-len(encoded))%4)
    tail=data[20+json_length:]
    path.write_bytes(struct.pack("<III",0x46546C67,2,20+len(encoded)+len(tail))+struct.pack("<II",len(encoded),0x4E4F534A)+encoded+tail)


def export(publish):
    scene=bpy.context.scene
    scene.view_settings.view_transform="Standard"
    scene.view_settings.look="None"
    scene.view_settings.exposure=0
    scene.view_settings.gamma=1
    scene.world.color=(.8,.7,.5)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"assets/studio/studio.blend"))
    if not publish:
        return
    batch_static()
    model=ROOT/"public/scene/studio.glb"
    bpy.ops.export_scene.gltf(filepath=str(model),export_format="GLB",export_cameras=True,export_extras=True,export_yup=True,export_apply=True,export_materials="EXPORT",export_animations=False,export_image_format="AUTO")
    normalize_unlit(model)
    metadata={"cameraTarget":[768,512,0],"horizontalLimitDegrees":8,"verticalLimitDegrees":4,"sourceSize":[1536,1024]}
    (ROOT/"public/scene/scene.json").write_text(json.dumps(metadata,indent=2)+"\n")


def main():
    arguments=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    parser=argparse.ArgumentParser()
    parser.add_argument("--finalize",action="store_true")
    parser.add_argument("--render",action="store_true")
    args=parser.parse_args(arguments)
    if args.finalize:
        bpy.ops.wm.open_mainfile(filepath=str(ROOT/"assets/studio/studio.blend"))
        api=Studio(ROOT)
        apply_atlas(api)
    else:
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        api=Studio(ROOT)
        print("SOURCE_PIXEL",api.pixels[50,50,:3].tolist(),flush=True)
        print("BUILD architecture",flush=True)
        build_architecture(api)
        print("BUILD observatory",flush=True)
        build_observatory(api)
        print("BUILD interiors",flush=True)
        build_interiors(api)
        fuse_architecture(api)
        print("BUILD tree",flush=True)
        before_tree=set(bpy.context.scene.objects)
        build_tree(api)
        for obj in set(bpy.context.scene.objects)-before_tree:
            obj.location.y+=300
        camera()
        bpy.context.view_layer.update()
        projection()
        build_motion(api)
    export(args.finalize)
    if args.render:
        bpy.context.scene.render.engine="CYCLES"
        bpy.context.scene.cycles.samples=8
        bpy.context.scene.render.filepath=str(ROOT/"assets/studio/blender-home.png")
        bpy.ops.render.render(write_still=True)
    print("STUDIO EXPORT COMPLETE",flush=True)


if __name__=="__main__":
    main()
