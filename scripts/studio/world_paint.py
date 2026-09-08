"""Attach source artwork to authored surfaces independently of the viewing camera."""
import json
import math
import shutil
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

from world import GEOMETRY, project

ROOT=Path(__file__).resolve().parents[2]
VIEWS={"view-front":"Codex Image Sep 7, 2026, 12_09_36 AM.png",
       "view-left":"Codex Image Sep 7, 2026, 12_09_32 AM.png",
       "view-rear":"Codex Image Sep 7, 2026, 12_12_23 AM.png",
       "view-top":"Codex Image Sep 7, 2026, 12_18_28 AM.png"}

STOREYS={name:(*storey["x"],*storey["y"],*storey["z"]) for name,storey in GEOMETRY["storeys"].items()}


def bilinear(quad,s,t):
    a,b,c,d=(Vector(point) for point in quad)
    return a*(1-s)*(1-t)+b*s*(1-t)+c*s*t+d*(1-s)*t


def layers(obj):
    mesh=obj.data
    uv=mesh.uv_layers.get("PaintUV") or mesh.uv_layers.new(name="PaintUV")
    depth=mesh.attributes.get("PaintDepth") or mesh.attributes.new(name="PaintDepth",type="FLOAT",domain="CORNER")
    return uv,depth


def paint_source_positions(obj,depth_offset=0):
    source=obj.data.attributes.get("SourcePosition")
    if source is None:
        uv,depth=layers(obj)
        for loop in obj.data.loops:
            uv.data[loop.index].uv=(10/1536,1-10/1024)
            depth.data[loop.index].value=999
        obj["sourceView"]="swatch"
        return
    uv,depth=layers(obj)
    for loop in obj.data.loops:
        u,v,d=source.data[loop.vertex_index].vector
        uv.data[loop.index].uv=(u/1536,1-v/1024)
        depth.data[loop.index].value=d+depth_offset
    obj["sourceView"]="artwork"


def prepare_views():
    for key,name in VIEWS.items():
        shutil.copyfile(ROOT/name,ROOT/"assets/studio/textures"/(key+".png"))
    # The right elevation has no reference of its own; mirror the left one.
    left=bpy.data.images.load(str(ROOT/"assets/studio/textures/view-left.png"),check_existing=False)
    pixels=np.array(left.pixels[:],dtype=np.float32).reshape(left.size[1],left.size[0],4)
    right=bpy.data.images.new("view-right",left.size[0],left.size[1],alpha=True)
    right.pixels=pixels[:,::-1,:].ravel().tolist()
    right.filepath_raw=str(ROOT/"assets/studio/textures/view-right.png")
    right.file_format="PNG"
    right.save()
    bpy.data.images.remove(left)
    bpy.data.images.remove(right)
