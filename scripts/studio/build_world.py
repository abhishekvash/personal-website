"""Build the multi-view reconstruction using orthogonal, shared world geometry."""
import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
from common import Studio
from build import normalize_unlit, batch_static
from world import create_camera, legacy_to_world, project, unproject, metadata, AWAY
from world_architecture import build_world_architecture
from world_observatory import build_world_observatory
from world_paint import layers, paint_source_positions, paint_world_architecture, prepare_views
from interiors import build_interiors
from world_tree import build_world_tree

WORK=ROOT/"assets/studio"


def setting(api):
    vertices=[(-2000,-1800,0),(3400,-1800,0),(3400,1070,0),(-2000,1070,0)]
    vertices += [(x,y,-30) for x,y,z in vertices.copy()]
    faces=[(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
    mesh=bpy.data.meshes.new("Setting_Table")
    mesh.from_pydata(vertices,[],faces)
    obj=bpy.data.objects.new("Setting_SolidTable",mesh)
    api.collection.objects.link(obj)
    mesh.materials.append(api.material("world-table" if (api.output/"textures/world-table.png").exists() else "background"))
    mesh.materials.append(api.material("wood"))
    uv=mesh.uv_layers.new(name="ArtworkUV")
    for polygon in mesh.polygons:
        if polygon.index>0:polygon.material_index=1
        for index in polygon.loop_indices:
            p=project(mesh.vertices[mesh.loops[index].vertex_index].co)
            uv.data[index].uv=(p.x/1536,1-p.y/1024)
    obj["coordinateSpace"]="world"
    obj["sourceFill"]="wood"
    obj=api.mesh("Setting_PaperBackdrop",[(-1700,-1200,1400),(3300,-1200,1400),(3300,1500,1400),(-1700,1500,1400)],[(0,1,2,3)],"paper-background")
    legacy_to_world(obj)


def source_projection():
    objects,triangles,owners,face_ids=[],[],[],[]
    for obj in bpy.context.scene.objects:
        if obj.type!="MESH" or obj.name.startswith(("Setting","Steam","FallingPetal","ScreenGlow")):
            continue
        mesh=obj.data
        uv=mesh.uv_layers.get("PaintUV")
        depths=mesh.attributes.get("PaintDepth")
        if uv is None or depths is None:
            raise ValueError(f"Unpainted object {obj.name}")
        mesh.calc_loop_triangles()
        groups=json.loads(obj.get("surfaceGroups","{}")) or {"": {"faces":list(range(len(mesh.polygons))),"fill":obj.get("sourceFill","blue"),"view":obj.get("sourceView","artwork")}}
        assigned=set()
        for label,group in groups.items():
            face_set=set(group["faces"])
            if not face_set:continue
            selected=[tri for tri in mesh.loop_triangles if tri.polygon_index in face_set]
            if not selected:continue
            index=len(objects)
            points=[]
            for tri in selected:
                coords=[]
                for loop in tri.loops:
                    tex=uv.data[loop].uv
                    coords.append((tex.x*1536,(1-tex.y)*1024,depths.data[loop].value))
                triangles.append(coords)
                points.extend(coords)
                owners.append(index)
                face_ids.append(tri.polygon_index)
            points=np.array(points)
            objects.append({"name":obj.name+("::"+label if label else ""),"object":obj.name,"faces":sorted(face_set),"source":True,"fill":group["fill"],"view":group.get("view",obj.get("sourceView","artwork")),"bounds":[float(points[:,0].min()),float(points[:,1].min()),float(points[:,0].max()),float(points[:,1].max())]})
            assigned|=face_set
        if assigned!=set(range(len(mesh.polygons))):
            raise ValueError(f"Unassigned paint faces on {obj.name}")
    np.savez_compressed(WORK/"world-projection.npz",triangles=np.array(triangles,dtype=np.float32),owners=np.array(owners,dtype=np.int32),face_ids=np.array(face_ids,dtype=np.int32))
    (WORK/"world-projection.json").write_text(json.dumps(objects)+"\n")
    print(f"SOURCE OWNERSHIP {len(objects)} surfaces / {len(triangles)} triangles",flush=True)


def place_roof_accessories():
    """Fit independent roof attachments while preserving their solid construction."""
    for obj in bpy.context.scene.objects:
        if obj.type!="MESH" or not obj.name.startswith("WorldObservatory_"):continue
        name=obj.name.removeprefix("WorldObservatory_")
        for vertex in obj.data.vertices:
            p=vertex.co
            if name.startswith("Antenna"):
                if name in ("AntennaPlinth","AntennaRaisedFoot"):
                    p.x=169+(p.x-169)*1.25
                    p.y=135+(p.y-135)*1.25
                p.x+=27
                p.y+=100
                p.z=690+(p.z-690)*1.2
            elif name=="Chimney":
                p.x+=6
                p.y-=15
                p.z=690+(p.z-690)*1.2
            else:
                p.x+=33
        obj.data.update()


def apply_atlas(api):
    spec=json.loads((WORK/"world-atlas.json").read_text())
    materials={}
    for info in spec["objects"].values():
        obj=bpy.data.objects[info["object"]]
        mesh=obj.data
        uv=mesh.uv_layers.get("PaintUV")
        fill_index=len(mesh.materials)
        mesh.materials.append(api.material(info["fill"]))
        if "page" in info:
            page=info["page"]
            if page not in materials:
                material=api.material(f"world-atlas-{page}")
                for node in material.node_tree.nodes:
                    if node.type=="TEX_IMAGE":
                        node.image=bpy.data.images.load(str(api.output/"textures"/f"world-atlas-{page}.png"),check_existing=False)
                materials[page]=material
            atlas_index=len(mesh.materials)
            mesh.materials.append(materials[page])
        visible=set(info.get("visibleFaces",[]))
        for face in info["faces"]:
            polygon=mesh.polygons[face]
            polygon.material_index=atlas_index if face in visible else fill_index
            for index in polygon.loop_indices:
                if face in visible:
                    u,v=uv.data[index].uv
                    x0,y0,_,_=info["bounds"]
                    x,y=info["origin"]
                    uv.data[index].uv=((x+u*1536-x0)/spec["size"],1-(y+(1-v)*1024-y0)/spec["size"])
                else:
                    p=obj.matrix_world @ mesh.vertices[mesh.loops[index].vertex_index].co
                    normal=polygon.normal
                    pair=(p.y,p.z) if abs(normal.x)>.7 else (p.x,p.y) if abs(normal.z)>.7 else (p.x,p.z)
                    uv.data[index].uv=(pair[0]/110,pair[1]/110)
    for obj in bpy.context.scene.objects:
        if obj.type!="MESH" or obj.data.uv_layers.get("PaintUV") is None:continue
        mesh=obj.data
        for layer in list(mesh.uv_layers):
            if layer.name!="PaintUV":mesh.uv_layers.remove(layer)
        mesh.uv_layers.active_index=0
        mesh.uv_layers[0].active_render=True


def export(publish):
    scene=bpy.context.scene
    scene.view_settings.view_transform="Standard"
    scene.view_settings.look="None"
    scene.world.color=(.8,.7,.5)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(WORK/"world-studio.blend"))
    if not publish:return
    batch_static()
    path=ROOT/"public/scene/studio-world.glb"
    bpy.ops.export_scene.gltf(filepath=str(path),export_format="GLB",export_cameras=True,export_extras=True,export_yup=True,export_apply=True,export_materials="EXPORT",export_animations=False,export_image_format="AUTO")
    normalize_unlit(path)
    (ROOT/"public/scene/scene-world.json").write_text(json.dumps(metadata())+"\n")


def main():
    args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    parser=argparse.ArgumentParser()
    parser.add_argument("--finalize",action="store_true")
    parser.add_argument("--draft",action="store_true")
    options=parser.parse_args(args)
    if options.finalize:
        bpy.ops.wm.open_mainfile(filepath=str(WORK/"world-studio.blend"))
        if bpy.context.scene.get("worldAtlasApplied") or bpy.context.scene.get("worldDraft"):
            raise RuntimeError("Finalization requires a fresh painted build. Run rebuild.py to regenerate original surface UVs.")
        api=Studio(ROOT)
        apply_atlas(api)
        table=bpy.data.objects.get("Setting_SolidTable")
        if table and (api.output/"textures/world-table.png").exists():
            material=api.material("world-table")
            for node in material.node_tree.nodes:
                if node.type=="TEX_IMAGE":
                    node.image=bpy.data.images.load(str(api.output/"textures/world-table.png"),check_existing=False)
            table.data.materials[0]=material
        bpy.context.scene["worldAtlasApplied"]=True
        export(True)
        return
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene["worldAtlasApplied"]=False
    bpy.context.scene["worldDraft"]=options.draft
    api=Studio(ROOT)
    prepare_views()
    rooms=build_world_architecture(api)
    print("WORLD ARCHITECTURE",flush=True)
    build_world_observatory(api)
    print("WORLD OBSERVATORY",flush=True)
    build_interiors(api)
    from world_interiors import adapt_interiors_to_world
    adapt_interiors_to_world(api,rooms)
    for obj in bpy.context.scene.objects:
        if obj.type=="MESH" and obj.name.startswith("Interior_"):paint_source_positions(obj)
    print("WORLD INTERIORS",flush=True)
    build_world_tree(api)
    from world_motion import build_world_motion
    build_world_motion(api)
    setting(api)
    create_camera()
    bpy.context.view_layer.update()
    if not options.draft:
        paint_world_architecture(api,rooms)
        from world_observatory_paint import paint_world_observatory
        paint_world_observatory(api)
        source_projection()
    place_roof_accessories()
    export(options.draft)
    print("WORLD BUILD COMPLETE",flush=True)


if __name__=="__main__":main()
