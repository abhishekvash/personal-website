"""Small, independent ambient elements. Source steam is removed before baking."""

import json
import math

import bpy
from mathutils import Vector

from common import HEIGHT


def center_origin(obj, center):
    offset=Vector((center[0],center[2],HEIGHT-center[1]))
    for vertex in obj.data.vertices:
        vertex.co-=offset
    obj.location=offset


def plume_material(api, name):
    material=bpy.data.materials.new(name)
    material.use_nodes=True
    material.surface_render_method="BLENDED"
    nodes=material.node_tree.nodes
    shader=nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value=(0,0,0,1)
    shader.inputs["Roughness"].default_value=1
    shader.inputs["Emission Strength"].default_value=1
    texture=nodes.new("ShaderNodeTexImage")
    texture.image=bpy.data.images.load(str(api.output/"textures"/f"{name}.png"),check_existing=True)
    material.node_tree.links.new(texture.outputs["Color"],shader.inputs["Emission Color"])
    material.node_tree.links.new(texture.outputs["Alpha"],shader.inputs["Alpha"])
    return material


def build_motion(api):
    for index,item in enumerate(json.loads((api.root/"assets/studio/motion.json").read_text())):
        x0,y0,x1,y1=item["bounds"]
        center=((x0+x1)/2,(y0+y1)/2,125)
        vertices=[]
        for i in range(5):
            y=y0+(y1-y0)*i/4
            d=125+math.sin(i*math.pi/4)*4
            vertices.extend([(x0,y,d),(x1,y,d)])
        obj=api.mesh(item["name"],vertices,[(i*2,i*2+1,i*2+3,i*2+2) for i in range(4)],"cream")
        obj.data.materials.clear()
        obj.data.materials.append(plume_material(api,item["texture"]))
        uv=obj.data.uv_layers.active
        for loop in obj.data.loops:
            u,v,_=vertices[loop.vertex_index]
            uv.data[loop.index].uv=((u-x0)/(x1-x0),1-(v-y0)/(y1-y0))
        center_origin(obj,center)
        obj["motion"]={"duration":7+index*2,"phase":0,"drift":2.5,"rise":12}

    for index,(u,v,d) in enumerate([(1160,425,195),(1410,435,205),(1220,310,190)]):
        vertices=[(u,v-7,d-1),(u+4,v-4,d+1),(u+3,v+3,d+2),(u,v+7,d),(u-4,v+2,d+1),(u-3,v-4,d+2),(u,v,d-2)]
        faces=[(6,i,(i+1)%6) for i in range(6)]
        obj=api.mesh(f"FallingPetal{index+1:02}",vertices,faces,"pink")
        center_origin(obj,(u,v,d))
        obj["motion"]={"duration":13+index*2,"phase":index*.3,"drift":-18,"rise":-85}
    for index,(quad,depth) in enumerate([
        ([(680,336),(773,328),(775,399),(681,409)],103),
        ([(858,516),(922,521),(928,579),(858,562)],131),
        ([(500,753),(573,745),(573,803),(500,811)],116),
    ]):
        obj=api.polygon(f"ScreenGlow{index+1:02}",quad,depth,"pink")
        obj["motion"]={"duration":9+index,"phase":index*.21}
