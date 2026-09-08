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
from world_paint import layers, paint_source_positions, prepare_views
from interiors import build_interiors
from world_tree import build_world_tree

WORK=ROOT/"assets/studio"


def _frame_split(obj):
    """Cut a large surface along the painting's frame so in-frame faces are exact."""
    import bmesh
    from world import RIGHT, UP, SCALE, IMAGE_ANCHOR
    mesh=bmesh.new()
    mesh.from_mesh(obj.data)
    planes=[(RIGHT,(0-IMAGE_ANCHOR.x)/SCALE),(RIGHT,(1536-IMAGE_ANCHOR.x)/SCALE),
            (UP,(IMAGE_ANCHOR.y-1024)/SCALE),(UP,(IMAGE_ANCHOR.y-0)/SCALE)]
    for normal,offset in planes:
        geometry=list(mesh.verts)+list(mesh.edges)+list(mesh.faces)
        bmesh.ops.bisect_plane(mesh,geom=geometry,plane_co=normal*offset,plane_no=normal,dist=.0001)
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()


def setting(api):
    from world import AWAY, RIGHT, unproject
    # A generous tabletop: the orbit must never reveal its edges.
    vertices=[(-7000,-7000,0),(9000,-7000,0),(9000,9000,0),(-7000,9000,0)]
    vertices += [(x,y,-30) for x,y,z in vertices.copy()]
    faces=[(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
    mesh=bpy.data.meshes.new("Setting_Table")
    mesh.from_pydata(vertices,[],faces)
    obj=bpy.data.objects.new("Setting_SolidTable",mesh)
    api.collection.objects.link(obj)
    mesh.materials.append(api.material("wood"))
    obj["coordinateSpace"]="world"
    obj["sourceFill"]="wood"
    obj["paintErode"]=8
    _frame_split(obj)
    # A vertical paper wall far behind the studio, square to the camera's heading.
    center=unproject((768,300,1400))
    across=RIGHT*9000
    up=Vector((0,0,1))
    corners=[center-across-up*4000,center+across-up*4000,center+across+up*6000,center-across+up*6000]
    mesh=bpy.data.meshes.new("Setting_Backdrop")
    mesh.from_pydata([tuple(c) for c in corners],[],[(0,1,2,3)])
    obj=bpy.data.objects.new("Setting_PaperBackdrop",mesh)
    api.collection.objects.link(obj)
    mesh.materials.append(api.material("paper"))
    obj["coordinateSpace"]="world"
    obj["sourceFill"]="paper"
    obj["paintErode"]=4
    obj["paintKeepColor"]="paper"
    mesh.update()
    if mesh.polygons[0].normal.dot(-AWAY)<0:
        mesh.polygons.foreach_set("use_smooth",[False])
        import bmesh
        b=bmesh.new(); b.from_mesh(mesh); bmesh.ops.reverse_faces(b,faces=list(b.faces)); b.to_mesh(mesh); b.free()
    _frame_split(obj)


def source_projection():
    """Export every surface group with its owning view and its triangles in every view.

    All triangles are occluders in every view; ownership belongs only to the
    view a group was painted from. Double-painted ink (the bonsai) exists in
    the reference view alone.
    """
    from world import ALL_VIEWS
    from world_projection_paint import EXCLUDED_PREFIXES
    views=list(ALL_VIEWS)
    objects,owners,face_ids=[],[],[]
    triangles={view:[] for view in views}
    for obj in bpy.context.scene.objects:
        if obj.type!="MESH" or obj.name.startswith(EXCLUDED_PREFIXES):
            continue
        mesh=obj.data
        if mesh.uv_layers.get("PaintUV") is None or mesh.attributes.get("PaintDepth") is None:
            raise ValueError(f"Unpainted object {obj.name}")
        mesh.calc_loop_triangles()
        groups=json.loads(obj.get("surfaceGroups","{}"))
        if not groups:
            raise ValueError(f"No surface groups on {obj.name}")
        double=obj.get("paintMode") in ("double","cards")
        matrix=obj.matrix_world
        world=[matrix @ vertex.co for vertex in mesh.vertices]
        projected={view:[ALL_VIEWS[view].project(point) for point in world] for view in views if not (double and view!="artwork")}
        assigned=set()
        for label,group in groups.items():
            face_set=set(group["faces"])
            if not face_set:continue
            selected=[tri for tri in mesh.loop_triangles if tri.polygon_index in face_set]
            if not selected:continue
            index=len(objects)
            view=group["view"]
            points=[]
            for tri in selected:
                for name in views:
                    if name not in projected:
                        triangles[name].append(((0,0,1e9),(0,0,1e9),(0,0,1e9)))
                        continue
                    coords=[tuple(projected[name][vertex]) for vertex in tri.vertices]
                    triangles[name].append(coords)
                    if name==view:
                        points.extend(coords)
                owners.append(index)
                face_ids.append(tri.polygon_index)
            if view=="swatch":
                bounds=[0.0,0.0,0.0,0.0]
            else:
                array=np.array(points)
                bounds=[float(array[:,0].min()),float(array[:,1].min()),float(array[:,0].max()),float(array[:,1].max())]
            objects.append({"name":obj.name+("::"+label if label else ""),"object":obj.name,"faces":sorted(face_set),"source":True,"fill":group["fill"],"view":view,"blend":group.get("blend",1.0),"erode":int(obj.get("paintErode",0)),"keepColor":obj.get("paintKeepColor",""),"card":group.get("card"),"bounds":bounds})
            assigned|=face_set
        if assigned!=set(range(len(mesh.polygons))):
            raise ValueError(f"Unassigned paint faces on {obj.name}")
    arrays={"tri_"+view:np.array(triangles[view],dtype=np.float32) for view in views}
    np.savez_compressed(WORK/"world-projection.npz",owners=np.array(owners,dtype=np.int32),face_ids=np.array(face_ids,dtype=np.int32),views=np.array(views),**arrays)
    (WORK/"world-projection.json").write_text(json.dumps(objects)+"\n")
    print(f"SOURCE OWNERSHIP {len(objects)} surfaces / {len(owners)} triangles / {len(views)} views",flush=True)


def build_rim(api):
    """Turn the baked silhouette rim into horizontal pixel-run quads at their solids' depth."""
    path=WORK/"world-rim.npz"
    if not path.is_file():return
    data=np.load(path)
    mask,depth=data["mask"],data["depth"]
    vertices,faces,uvs=[],[],[]
    for y in range(mask.shape[0]):
        row=mask[y]
        x=0
        while x<row.shape[0]:
            if not row[x]:
                x+=1;continue
            start=x
            d=float(depth[y,x])
            while x<row.shape[0] and row[x] and abs(float(depth[y,x])-d)<3:
                x+=1
            base=len(vertices)
            corners=[(start,y),(x,y),(x,y+1),(start,y+1)]
            for u,v in corners:
                vertices.append(unproject((u,v,d)))
                uvs.append((u/1536,1-v/1024))
            faces.append((base,base+1,base+2,base+3))
    mesh=bpy.data.meshes.new("WorldRim")
    mesh.from_pydata([tuple(v) for v in vertices],[],faces)
    obj=bpy.data.objects.new("WorldRim",mesh)
    api.collection.objects.link(obj)
    mesh.materials.append(api.material("paper"))
    uv=mesh.uv_layers.new(name="PaintUV")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            uv.data[loop_index].uv=uvs[mesh.loops[loop_index].vertex_index]
    obj["coordinateSpace"]="world"
    obj["sourceFill"]="paper"
    print(f"WORLD RIM {len(faces)} pixel runs",flush=True)
    return obj


def cutout_material(api,page):
    """An unlit, alpha-masked page for blossom cards; alpha travels with the image."""
    material=bpy.data.materials.new(f"world-atlas-{page}")
    material.use_nodes=True
    nodes=material.node_tree.nodes
    nodes.clear()
    output=nodes.new("ShaderNodeOutputMaterial")
    principled=nodes.new("ShaderNodeBsdfPrincipled")
    texture=nodes.new("ShaderNodeTexImage")
    texture.image=bpy.data.images.load(str(api.output/"textures"/f"world-atlas-{page}.png"),check_existing=False)
    texture.interpolation="Linear"
    links=material.node_tree.links
    links.new(principled.outputs[0],output.inputs["Surface"])
    links.new(texture.outputs["Color"],principled.inputs["Emission Color"])
    links.new(texture.outputs["Alpha"],principled.inputs["Alpha"])
    principled.inputs["Emission Strength"].default_value=1
    principled.inputs["Base Color"].default_value=(0,0,0,1)
    material.surface_render_method="DITHERED"
    material.use_backface_culling=False
    return material


def apply_atlas(api):
    rim=build_rim(api)
    spec=json.loads((WORK/"world-atlas.json").read_text())
    if rim is not None and "WorldRim" in spec["objects"]:
        spec["objects"]["WorldRim"]["faces"]=list(range(len(rim.data.polygons)))
        spec["objects"]["WorldRim"]["visibleFaces"]=list(range(len(rim.data.polygons)))
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
                if str(page).startswith("cutout"):
                    materials[page]=cutout_material(api,page)
                else:
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
                    size=info.get("size",spec["size"])
                    uv.data[index].uv=((x+u*1536-x0)/size,1-(y+(1-v)*1024-y0)/size)
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
    bpy.ops.export_scene.gltf(filepath=str(path),export_format="GLB",export_cameras=True,export_extras=True,export_yup=True,export_apply=True,export_materials="EXPORT",export_animations=False,export_image_format="WEBP",export_image_quality=92,export_normals=False,export_meshopt_compression_enable=True)
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
    print("WORLD INTERIORS",flush=True)
    build_world_tree(api)
    from world_motion import build_world_motion
    build_world_motion(api)
    setting(api)
    create_camera()
    bpy.context.view_layer.update()
    if not options.draft:
        from world_projection_paint import paint_scene
        paint_scene()
        source_projection()
    export(options.draft)
    print("WORLD BUILD COMPLETE",flush=True)


if __name__=="__main__":main()
