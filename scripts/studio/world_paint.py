"""Attach source artwork to authored surfaces independently of the viewing camera."""
import json
import math
import shutil
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

from world import project

ROOT=Path(__file__).resolve().parents[2]
VIEWS={"view-front":"Codex Image Sep 7, 2026, 12_09_36 AM.png",
       "view-right":"Codex Image Sep 7, 2026, 12_09_29 AM.png",
       "view-rear":"Codex Image Sep 7, 2026, 12_12_23 AM.png",
       "view-top":"Codex Image Sep 7, 2026, 12_18_28 AM.png"}

# Each quad is ordered top-left, top-right, bottom-right, bottom-left in the
# source drawing. World surfaces remain planar; only their paint is fitted.
FRONT={"Ground":[(454,708),(1098,643),(1107,924),(438,982)],
       "Recording":[(471,492),(1068,477),(1075,681),(460,714)],
       "Gaming":[(488,317),(1019,278),(1024,464),(482,525)]}
SIDE={"Ground":[(331,619),(455,705),(441,957),(309,855)],
      "Recording":[(368,446),(469,503),(456,696),(343,615)],
      "Gaming":[(398,276),(488,317),(482,490),(382,443)]}
REAR={"Ground":[(558,700),(1221,700),(1221,857),(558,857)],
      "Recording":[(595,520),(1184,520),(1184,672),(595,672)],
      "Gaming":[(627,332),(1153,332),(1153,493),(627,493)]}
STOREYS={"Ground":(0,700,0,420,40,280),"Recording":(25,675,27.5,392.5,280,475),"Gaming":(57.5,642.5,55,365,475,690)}


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


def _architecture_surface(point,normal,region,rooms):
    # Give source-exclusive swatches to faces never established by a reference.
    for room_name,room in rooms.items():
        if not region.startswith(room_name+" ") or "front facade" in region or "exterior" in region or "deck" in region:
            continue
        x0,y0,z1=room["x"][0],room["y"][0],room["ceilingZ"]
        if "rear wall" in region:
            return Vector((100+(point.x-x0)*2,100+(z1-point.z)*2)),350,"wall-"+room_name+"-rear"
        if "right wall" in region:
            return Vector((100+(point.y-y0)*2,100+(z1-point.z)*2)),350,"wall-"+room_name+"-right"
        if "floor" in region:
            return Vector((100+(point.x-x0)*2,100+(point.y-y0)*2)),300,"floor-"+room_name
        if "ceiling" in region:
            return Vector((10,10)),999,"swatch"
        return Vector((10,10)),999,"swatch"
    level=next((name for name in STOREYS if region.startswith(name+" ")),None)
    if level:
        x0,x1,y0,y1,z0,z1=STOREYS[level]
        sx=(point.x-x0)/(x1-x0)
        sy=(point.y-y0)/(y1-y0)
        sz=(z1-point.z)/(z1-z0)
        if "front facade" in region or normal.y<-.8:
            return bilinear(FRONT[level],sx,sz),-8,"architecture-front"
        if normal.x<-.7:
            return bilinear(SIDE[level],1-sy,sz),250*sy,"architecture-sides"
        if normal.y>.7:
            return bilinear(REAR[level],1-sx,sz),0,"view-rear"
        if normal.x>.7:
            # A separate reference owns the opposite side; the front image's
            # neighboring paper and tree can never become a wall texture.
            right_quads={"Ground":[(902,715),(1035,647),(1048,824),(905,935)],"Recording":[(889,511),(1008,453),(1012,628),(895,697)],"Gaming":[(878,304),(971,260),(980,441),(883,489)]}
            return bilinear(right_quads[level],sy,sz),0,"architecture-right"
        if "deck" in region:
            if level=="Gaming":
                quad=[(398,265),(847,237),(1015,279),(488,314)]
            elif level=="Recording":
                quad=[(363,438),(1021,453),(1069,481),(473,517)]
            else:
                quad=[(333,607),(1064,625),(1100,669),(462,720)]
            return bilinear(quad,sx,1-sy),160*sy,"architecture-roofs"
    return Vector((10,10)),999,"swatch"


def paint_world_architecture(api,rooms):
    for obj in bpy.context.scene.objects:
        if obj.type!="MESH" or not obj.name.startswith("WorldArchitecture_"):
            continue
        mesh=obj.data
        uv,depth=layers(obj)
        groups=json.loads(obj.get("surfaceGroups","{}"))
        if obj.name=="WorldArchitecture_BuildingShell":
            painted_groups={}
            for label,group in groups.items():
                region=label.split(":")[0]
                for index in group["faces"]:
                    polygon=mesh.polygons[index]
                    normal=obj.matrix_world.to_3x3() @ polygon.normal
                    painted_region=region
                    fill=group["fill"]
                    center=obj.matrix_world @ polygon.center
                    if region=="Workspace inner wall and fillet" and normal.x<-.5 and center.y>rooms["Workspace"]["frontY"]+12:
                        painted_region="Workspace right wall"
                    if painted_region=="Workspace right wall":
                        fill="pink"
                    view="swatch"
                    for loop_index in polygon.loop_indices:
                        point=obj.matrix_world @ mesh.vertices[mesh.loops[loop_index].vertex_index].co
                        p,d,view=_architecture_surface(point,normal,painted_region,rooms)
                        uv.data[loop_index].uv=(p.x/1536,1-p.y/1024)
                        depth.data[loop_index].value=d
                    # Retain each physical plane/curved face's existing owner.
                    # Only the workspace wall's semantic region changes here.
                    key=painted_region+":"+label.partition(":")[2]
                    entry=painted_groups.setdefault(key,{"faces":[],"fill":fill,"view":view})
                    entry["faces"].append(index)
            groups=painted_groups
        else:
            # Small fittings receive their own crop, shared across the fitting's
            # surfaces. Each still owns only its source-visible front polygons.
            box=None
            source_view="artwork"
            if "GamingServiceVent" in obj.name:
                box=(515,369,578,482)
            elif "RecordingFrontPorthole" in obj.name:
                box=(1001,522,1056,594)
            elif "Porthole" in obj.name and "Left" in obj.name:
                box=(342,707,376,748) if "Small" in obj.name else ((373,746,422,830) if "Ground" in obj.name else (380,515,433,602) if "Recording" in obj.name else (414,332,456,413))
            elif "GamingRightPorthole" in obj.name:
                box=(884,330,944,419)
            elif "Right" in obj.name and "Porthole" in obj.name:
                box=(979,713,1019,753) if "Small" in obj.name else (938,751,980,826) if "Ground" in obj.name else (938,522,982,607)
                source_view="view-right"
            if box:
                points=[project(obj.matrix_world @ vertex.co) for vertex in mesh.vertices]
                # Rims and glass of one opening share the same source crop.
                related=[other for other in bpy.context.scene.objects if other.type=="MESH" and other.name.rsplit("_",1)[0]==obj.name.rsplit("_",1)[0]]
                all_points=[project(other.matrix_world @ vertex.co) for other in related for vertex in other.data.vertices]
                x0,x1=min(p.x for p in all_points),max(p.x for p in all_points)
                y0,y1=min(p.y for p in all_points),max(p.y for p in all_points)
                for loop in mesh.loops:
                    p=points[loop.vertex_index]
                    u=box[0]+(p.x-x0)/max(1,x1-x0)*(box[2]-box[0])
                    v=box[1]+(p.y-y0)/max(1,y1-y0)*(box[3]-box[1])
                    uv.data[loop.index].uv=(u/1536,1-v/1024)
                    depth.data[loop.index].value=(-20 if "Glass" not in obj.name else -10)+p.z*.001
                for group in groups.values():group["view"]=source_view
            else:
                for group in groups.values():group["view"]="swatch"
        obj["surfaceGroups"]=json.dumps(groups)


def prepare_views():
    for key,name in VIEWS.items():
        shutil.copyfile(ROOT/name,ROOT/"public/scene/textures"/(key+".png"))
