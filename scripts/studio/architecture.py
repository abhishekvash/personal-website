"""Closed cutaway storeys with shared wall, ceiling, floor, and roof boundaries."""

import json
import math

import bmesh
import bpy
from mathutils import Vector

from common import rounded_quad, triangulate


ROOF_FRONT = [(488, 306, -8), (982, 267, -8)]
ROOF_BACK = [(398,265,330),(620,237,330),(847,237,330),(1007,260,150)]


def plane_depth(u, v, triangle):
    a, b, c = triangle
    divisor = (b[1]-c[1])*(a[0]-c[0]) + (c[0]-b[0])*(a[1]-c[1])
    if abs(divisor) < 1e-8:
        raise ValueError("Collapsed architectural surface")
    w0 = ((b[1]-c[1])*(u-c[0]) + (c[0]-b[0])*(v-c[1])) / divisor
    w1 = ((c[1]-a[1])*(u-c[0]) + (a[0]-c[0])*(v-c[1])) / divisor
    w2 = 1-w0-w1
    return w0*a[2] + w1*b[2] + w2*c[2], min(w0, w1, w2)


def roof_depth(u, v):
    outline = [*ROOF_FRONT, *reversed(ROOF_BACK)]
    triangles = triangulate([[Vector((x, y, 0)) for x, y, _ in outline]])
    choices = [plane_depth(u, v, [outline[i] for i in triangle]) for triangle in triangles]
    depth, _ = max(choices, key=lambda choice: choice[1])
    return max(-8, min(330, depth))


def close_normals(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    bmesh.ops.remove_doubles(mesh, verts=list(mesh.verts), dist=.0001)
    bmesh.ops.recalc_face_normals(mesh, faces=list(mesh.faces))
    if mesh.calc_volume(signed=True) < 0:
        bmesh.ops.reverse_faces(mesh, faces=list(mesh.faces))
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()


def material_groups(obj, fills):
    """Give each connected planar surface its own source ownership mask."""
    mesh=obj.data
    neighbors={polygon.index:set() for polygon in mesh.polygons}
    edges={}
    for polygon in mesh.polygons:
        for edge in polygon.edge_keys:
            key=tuple(sorted(edge))
            for other in edges.get(key,[]):
                neighbors[polygon.index].add(other)
                neighbors[other].add(polygon.index)
            edges.setdefault(key,[]).append(polygon.index)
    remaining=set(neighbors)
    groups={}
    while remaining:
        first=min(remaining)
        reference=mesh.polygons[first]
        remaining.remove(first)
        pending=[first]
        faces=[]
        while pending:
            index=pending.pop()
            faces.append(index)
            for candidate in neighbors[index] & remaining:
                polygon=mesh.polygons[candidate]
                if polygon.material_index != reference.material_index:
                    continue
                if polygon.normal.dot(reference.normal)<.9998:
                    continue
                if any(abs((mesh.vertices[i].co-reference.center).dot(reference.normal))>.2 for i in polygon.vertices):
                    continue
                remaining.remove(candidate)
                pending.append(candidate)
        groups[str(len(groups))]={"faces":sorted(faces),"fill":fills[reference.material_index]}
    obj["surfaceGroups"]=json.dumps(groups)


def closed_prism(api, name, front, back, fill="cream"):
    """Corresponding loops define a closed volume, including both end caps."""
    count = len(front)
    assert count == len(back)
    cap = triangulate([[Vector((u, v, 0)) for u, v, _ in front]])
    faces = cap + [tuple(index+count for index in reversed(face)) for face in cap]
    faces += [(i, (i+1)%count, (i+1)%count+count, i+count) for i in range(count)]
    obj = api.mesh(name, front+back, faces)
    obj["sourceFill"] = fill
    close_normals(obj)
    return obj


def rounded_spatial(corners, radius, steps=7):
    result=[]
    for index,corner in enumerate(corners):
        current=Vector(corner)
        previous=Vector(corners[index-1])
        following=Vector(corners[(index+1)%len(corners)])
        before_length=math.hypot(previous.x-current.x,previous.y-current.y)
        after_length=math.hypot(following.x-current.x,following.y-current.y)
        first=current+(previous-current)*min(radius/before_length,.4)
        last=current+(following-current)*min(radius/after_length,.4)
        for step in range(steps):
            t=step/(steps-1)
            result.append(tuple(first*(1-t)**2+current*(2*t*(1-t))+last*t*t))
    return result


def shell(api, name, outer, rear, rooms, front_depth=-8, outer_radius=5):
    """A single manifold shell contains several front-open, closed-back rooms."""
    front_loop = rounded_quad(outer, outer_radius)
    outer_front = [(u, v, front_depth) for u, v in front_loop]
    outer_back = rounded_spatial(rear, outer_radius)
    rear_loop = [(u,v) for u,v,_ in outer_back]
    vertices = outer_front + outer_back
    count = len(front_loop)
    faces, fills = [], []
    def face(indices, fill):
        faces.append(tuple(indices))
        fills.append(fill)
    for i in range(count):
        face((i, (i+1)%count, (i+1)%count+count, i+count), "blue")
    for tri in triangulate([[Vector((u, v, 0)) for u, v in rear_loop]]):
        face(tuple(i+count for i in tri), "blue")

    front_polylines = [front_loop]
    front_indices = list(range(count))
    for room in rooms:
        inner = rounded_quad(room["front"], room.get("radius", 13))
        back = rounded_quad(room["rear"], room.get("radius", 13))
        first = len(vertices)
        vertices.extend((u, v, front_depth) for u, v in inner)
        end = len(vertices)
        vertices.extend((u, v, room["depth"]) for u, v in back)
        front_polylines.append(list(reversed(inner)))
        front_indices.extend(reversed(range(first, end)))
        n = len(inner)
        steps = n//4
        for i in range(n):
            # Each rounded room uses four equal corner spans. The joining
            # segments become walls, ceiling, and floor of the same solid.
            edge = i//steps
            fill = "cream" if edge == 0 else (room.get("floor", "gold") if edge == 2 else "gold")
            face((first+i, first+(i+1)%n, end+(i+1)%n, end+i), fill)
        for tri in triangulate([[Vector((u, v, 0)) for u, v in back]]):
            face(tuple(i+end for i in tri), room.get("rearFill", "pink"))
    cap = triangulate([[Vector((u, v, 0)) for u, v in loop] for loop in front_polylines])
    for tri in cap:
        face(tuple(front_indices[i] for i in tri), "cream")
    obj = api.mesh(name, vertices, faces)
    palette = ["cream", "blue", "gold", "pink", "ink"]
    for fill in palette[1:]:
        obj.data.materials.append(api.material(fill))
    for polygon, fill in zip(obj.data.polygons, fills):
        polygon.material_index = palette.index(fill)
    obj["sourceFill"] = "blue"
    close_normals(obj)
    material_groups(obj, palette)
    return obj


def recess_port(api, owner, name, center, radii, surface, interior=False):
    """A blind window recess cut into the solid, with a seated closed glass plug."""
    u, v = center
    rx, ry = radii
    bpy.context.view_layer.update()
    fallback=surface
    def surface(x,y):
        hit, location, _, _=owner.ray_cast(Vector((x,-2000,1024-y)),Vector((0,1,0)))
        if interior:
            return max(2, fallback(x,y))
        if not hit:
            return fallback(x,y)
        return location.y
    ring = [(u+rx*math.cos(i*math.tau/64), v+ry*math.sin(i*math.tau/64)) for i in range(64)]
    front = [(x, y, surface(x, y)-5) for x, y in ring]
    back = [(x, y, surface(x, y)+29) for x, y in ring]
    inside = [(u+(x-u)*.91, v+(y-v)*.94) for x, y in ring]
    glass_front=[(x,y,surface(x,y)+25) for x,y in inside]
    glass_back=[(x,y,d+7) for x,y,d in glass_front]
    rim_outer=[(u+(rx+1)*math.cos(i*math.tau/64),v+(ry+1)*math.sin(i*math.tau/64)) for i in range(64)]
    rim_inner=[(u+(rx-3)*math.cos(i*math.tau/64),v+(ry-3)*math.sin(i*math.tau/64)) for i in range(64)]
    rim_vertices=[(x,y,surface(x,y)+offset) for offset in (-1,5) for contour in (rim_outer,rim_inner) for x,y in contour]
    rim_faces=[]
    for i in range(64):
        j=(i+1)%64
        rim_faces += [(i,j,j+64,i+64),(i+128,i+192,j+192,j+128),(i,i+128,j+128,j),(i+64,j+64,j+192,i+192)]
    rim=api.mesh(name+" solid cream rim",rim_vertices,rim_faces)
    rim["sourceFill"]="cream"
    close_normals(rim)
    cutter = closed_prism(api, name+" cutter", front, back, "ink")
    cutter.data.materials.clear()
    cutter.data.materials.append(api.material("ink"))
    boolean = owner.modifiers.new(name+" recess", "BOOLEAN")
    boolean.operation = "DIFFERENCE"
    boolean.solver = "EXACT"
    boolean.object = cutter
    bpy.context.view_layer.objects.active = owner
    try:
        bpy.ops.object.modifier_apply(modifier=boolean.name)
    finally:
        bpy.data.objects.remove(cutter, do_unlink=True)
    # The plug's front and rear follow precisely the wall plane used by the cut.
    glass = closed_prism(api, name+" recessed blue glass", glass_front, glass_back, "ink")
    glass["sourceFill"] = "ink"
    close_normals(owner)
    material_groups(owner, ["cream", "blue", "gold", "pink", "ink"])


def side_depth(front_top, front_bottom, back_top, back_bottom):
    triangles = [(front_top, front_bottom, back_bottom), (front_top, back_bottom, back_top)]
    def depth(u, v):
        return max((plane_depth(u,v,tri) for tri in triangles), key=lambda entry: entry[1])[0]
    return depth


def setting(api):
    # Shared edge vertices make the extended table a closed slab. The original
    # image is used only on the central top, with wood continuing beyond it.
    xs=[-1400,0,1536,3000]
    vertices=[]
    for row in range(3):
        for u in xs:
            v=798-.0807096*u if row==0 else (1024 if row==1 else 2300)
            vertices.append((u,v,(986-v-.092*(u-460))*3))
    vertices += [(u,v+28,d) for u,v,d in vertices.copy()]
    faces=[]
    for row in range(2):
        for col in range(3):
            a=row*4+col
            faces.append((a,a+1,a+5,a+4))
    faces += [tuple(i+12 for i in reversed(face)) for face in faces.copy()]
    perimeter=[0,1,2,3,7,11,10,9,8,4]
    faces += [(a,b,b+12,a+12) for a,b in zip(perimeter,perimeter[1:]+perimeter[:1])]
    table=api.mesh("Setting • solid wooden tabletop",vertices,faces,"wood")
    table.data.materials.append(api.material("background"))
    table.data.polygons[1].material_index=1
    for loop_index in table.data.polygons[1].loop_indices:
        co=table.data.vertices[table.data.loops[loop_index].vertex_index].co
        table.data.uv_layers.active.data[loop_index].uv=(co.x/1536,co.z/1024)
    close_normals(table)
    api.mesh("Setting • paper backdrop", [(-1700,-1200,950),(3300,-1200,950),(3300,1500,950),(-1700,1500,950)], [(0,1,2,3)], "paper-background")


def build_architecture(api):
    setting(api)
    upper = shell(api, "Architecture • continuous upper storey",
        [(488,317),(665,303),(843,289),(982,278),(987,492),(580,525),(482,490)],
        [(u,v+11,depth) for u,v,depth in ROOF_BACK] + [(u,v,330-(u-398)*180/609) for u,v in [(1020,480),(476,505),(382,443)]],
        [{"front": [(602,324),(951,300),(964,474),(602,503)], "rear": [(594,318),(866,296),(870,459),(594,484)], "depth":165, "floor":"pink"}],
        outer_radius=3)
    middle = shell(api, "Architecture • continuous middle storey",
        [(471,492),(1068,477),(1075,681),(460,714)],
        [(u,v,350-(u-368)*140/691) for u,v in [(368,446),(1017,430),(1059,629),(343,639)]],
        [{"front": [(501,520),(965,496),(975,651),(491,691)], "rear": [(562,518),(954,498),(947,629),(561,645)], "depth":165,"floor":"pink", "radius":20}],
        front_depth=-8.5,outer_radius=13)
    lower = shell(api, "Architecture • continuous ground storey",
        [(454,708),(1098,643),(1107,924),(438,982)],
        [(u,v,360-(u-331)*170/773) for u,v in [(331,619),(1076,587),(1104,874),(309,893)]],
        [{"front": [(477,741),(752,712),(757,917),(466,949)], "rear": [(477,741),(754,710),(754,865),(477,889)], "depth":170, "radius":16},
         {"front": [(775,705),(1067,677),(1079,876),(778,914)], "rear": [(775,704),(1005,680),(1005,852),(775,875)], "depth":170, "rearFill":"gold", "radius":15}],
        front_depth=-9,outer_radius=16)

    recess_port(api,upper,"Architecture • upper side porthole",(435,371),(17,33),side_depth((488,317,-8),(482,490,-8),(398,276,330),(382,443,330)))
    recess_port(api,middle,"Architecture • middle side porthole",(407,558),(22,39),side_depth((471,492,-8.5),(460,714,-8.5),(368,446,350),(343,639,350)))
    lower_surface=side_depth((454,708,-9),(438,982,-9),(331,619,360),(309,893,360))
    for index,center,radii in [(1,(397,788),(22,38)),(2,(360,726),(9,16))]:
        recess_port(api,lower,f"Architecture • lower side porthole {index}",center,radii,lower_surface)
    recess_port(api,upper,"Architecture • gaming interior porthole",(915,371),(26,40),side_depth((951,300,-8),(964,474,-8),(866,296,165),(870,459,165)),interior=True)
    recess_port(api,middle,"Architecture • recording interior porthole",(500,595),(15,34),side_depth((501,520,-8.5),(491,691,-8.5),(562,518,165),(561,645,165)),interior=True)
    recess_port(api,middle,"Architecture • right pillar porthole",(1028,558),(23,32),lambda u,v:-8.5)

    # Roof underside overlaps the shared storey boundary by 1px. Its rear edge
    # retains the raised, slightly uneven outline painted in the reference.
    roof = [*ROOF_FRONT, *reversed(ROOF_BACK)]
    closed_prism(api,"Architecture • continuous solid roof",roof,[(u,v+12,d) for u,v,d in roof],"cream")
    # These sills extend into both adjoining shells. They are structural bands,
    # not disconnected plates fitted independently to the camera.
    for name,points,depth,thickness in [
        ("middle left sill",[(363,438),(477,492),(603,483),(604,512),(473,520),(361,461)],-13,29),
        ("ground perimeter sill",[(333,607),(465,691),(1093,638),(1103,648),(1100,672),(462,723),(332,634)],-15,25),
        ("base plinth",[(304,830),(331,845),(445,966),(1105,875),(1126,869),(1127,893),(1103,911),(1099,931),(452,989),(417,975),(300,853)],-16,33),
    ]:
        if name=="base plinth":
            front=[(u,v,max(-16,min(lower_surface(u,v),(986-v-.092*(u-460))*3-5))) for u,v in points]
            closed_prism(api,"Architecture • "+name,front,[(u,v-5,d+30) for u,v,d in front],"blue")
        else:
            front=[(u,v,depth+max(0,465-u)*2.6) for u,v in points]
            closed_prism(api,"Architecture • "+name,front,[(u,v+3,d+thickness) for u,v,d in front],"cream")
    # Each foot is a closed block whose lower edge meets the same tabletop plane.
    for index,(u,v,w,h) in enumerate([(451,976,21,18),(618,959,21,18),(836,934,20,17),(1071,917,23,18),(318,870,15,28)]):
        shape=rounded_quad([(u,v-4),(u+w,v-6),(u+w,v+h),(u,v+h+2)],3)
        front=[(x,y,(986-(v+h+2)-.092*(x-460))*3-5) for x,y in shape]
        back=[(x-6,y-6,d+24) for x,y,d in front]
        closed_prism(api,f"Architecture • solid foot {index+1}",front,back,"cream")
    vent=rounded_quad([(516,375),(576,369),(576,474),(517,480)],8)
    api.solid("Architecture • vent housing",vent,-11,16,side_material="cream")
    for i in range(9):
        y=387+i*9.1
        api.solid(f"Architecture • vent louver {i+1}",rounded_quad([(526,y),(568,y-3),(568,y+3),(526,y+6)],2),-15,8,side_material="cream")


def fuse_architecture(api):
    """Resolve intersecting storeys into one connected structural volume."""
    names=["Architecture • continuous "+label for label in ("ground storey","middle storey","upper storey","solid roof")]
    primary=bpy.data.objects[names[0]]
    for name in names[1:]:
        other=bpy.data.objects[name]
        boolean=primary.modifiers.new("Shared structural junction", "BOOLEAN")
        boolean.operation="UNION"
        boolean.solver="EXACT"
        boolean.object=other
        bpy.context.view_layer.objects.active=primary
        bpy.ops.object.modifier_apply(modifier=boolean.name)
        bpy.data.objects.remove(other,do_unlink=True)
    primary.name="Architecture • unified studio shell"
    primary["constructionParts"]=json.dumps(names)
    close_normals(primary)
    fills=["cream" if material.name=="source" else material.name for material in primary.data.materials]
    material_groups(primary,fills)
    for obj in bpy.context.scene.objects:
        for property_name in ("mountedTo","floorSupport","connectsSecond"):
            if obj.get(property_name) in names:
                obj[property_name]=primary.name
    return primary
