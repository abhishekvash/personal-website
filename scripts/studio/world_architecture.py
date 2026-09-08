"""Canonical solid architecture in world X (width), Y (depth), Z (height).

The front faces negative Y. No image coordinates or camera projection enter
the construction; the publishing pipeline assigns artwork and UVs afterward.
"""

import json

import bmesh
import bpy
from mathutils import Vector

from world import GEOMETRY


STOREYS = {name: {"bottom": storey["z"][0], "top": storey["z"][1]}
           for name, storey in GEOMETRY["storeys"].items()}
WALL = GEOMETRY["wall"]
CORNER_RADIUS = GEOMETRY["cornerRadius"]


def _finish(obj, fill="blue"):
    obj["coordinateSpace"] = "world"
    obj["sourceFill"] = fill
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    # Exact Boolean intersections can differ by a few float32 units around a
    # curved porthole. Weld those microscopic seams before recalculating faces.
    bmesh.ops.remove_doubles(mesh, verts=list(mesh.verts), dist=.0001)
    bmesh.ops.dissolve_degenerate(mesh, edges=list(mesh.edges), dist=.000001)
    bmesh.ops.recalc_face_normals(mesh, faces=list(mesh.faces))
    if mesh.calc_volume(signed=True) < 0:
        bmesh.ops.reverse_faces(mesh, faces=list(mesh.faces))
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()
    return obj


def _box(api, name, bounds, fill="blue", radius=0, segments=4):
    low = Vector((bounds[0], bounds[2], bounds[4]))
    high = Vector((bounds[1], bounds[3], bounds[5]))
    if any(high[axis] <= low[axis] for axis in range(3)):
        raise ValueError(f"Collapsed architectural box: {name}")
    bpy.ops.mesh.primitive_cube_add(size=1, location=(low + high) / 2)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = high - low
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(api.material(fill))
    if radius:
        bevel = obj.modifiers.new("Rounded manufactured edges", "BEVEL")
        bevel.width = min(radius, min(high - low) / 2 - .01)
        bevel.segments = segments
        bevel.affect = "EDGES"
        bpy.ops.object.modifier_apply(modifier=bevel.name)
    return _finish(obj, fill)


def _boolean(owner, cutter, operation="DIFFERENCE"):
    bpy.context.view_layer.objects.active = owner
    modifier = owner.modifiers.new("Solid " + operation.lower(), "BOOLEAN")
    modifier.operation = operation
    modifier.solver = "EXACT"
    modifier.object = cutter
    try:
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    finally:
        bpy.data.objects.remove(cutter, do_unlink=True)
    return _finish(owner, owner.get("sourceFill", "blue"))


def _cylinder(api, name, center, radius, length, axis, fill="ink", vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=length,
                                      end_fill_type="NGON", location=center)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = Vector(axis).to_track_quat("Z", "Y").to_euler()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.data.materials.append(api.material(fill))
    for polygon in obj.data.polygons:
        polygon.use_smooth = len(polygon.vertices) == 4
    return _finish(obj, fill)


def _torus(api, name, center, radius, tube, axis, fill="cream"):
    bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=tube,
                                   major_segments=64, minor_segments=12, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = Vector(axis).to_track_quat("Z", "Y").to_euler()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.data.materials.append(api.material(fill))
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return _finish(obj, fill)


def _surface_groups(obj, classify=None):
    """A material may span several planes, but never owns their shared artwork."""
    groups = {}
    matrix = obj.matrix_world
    normal_matrix = matrix.to_3x3()
    for polygon in obj.data.polygons:
        center = matrix @ polygon.center
        normal = (normal_matrix @ polygon.normal).normalized()
        region, fill = classify(center, normal) if classify else (obj.name, obj.get("sourceFill", "blue"))
        if max(abs(value) for value in normal) > .9999:
            # Disjoint portions of exactly the same plane cannot hide one
            # another; curved portions retain individual surface ownership.
            direction = tuple(round(value, 4) for value in normal)
            label = f"{region}:plane:{direction}:{normal.dot(center):.4f}"
        else:
            label = f"{region}:curved-face:{polygon.index}"
        group = groups.setdefault(label, {"faces": [], "fill": fill})
        group["faces"].append(polygon.index)
    obj["surfaceGroups"] = json.dumps(groups)


def _room_bounds():
    return json.loads(json.dumps(GEOMETRY["rooms"]))


def _carve_room(api, shell, name, room):
    left, right = room["x"]
    front, rear = room["y"]
    floor, ceiling = room["floorZ"], room["ceilingZ"]
    opening_left, opening_right = room["openingX"]
    front_pillar = opening_left != left or opening_right != right
    if front_pillar:
        # The chamber extends behind a real front pillar. Its entry joins the
        # larger cavity with a generous overlap so no dividing skin remains.
        chamber = _box(api, f"WorldArchitecture_{name}_ChamberCutter",
                       (left, right, front + 25, rear, floor, ceiling), radius=10, segments=6)
        opening = _box(api, f"WorldArchitecture_{name}_OpeningCutter",
                       (opening_left, opening_right, front - 40, front + 50, floor, ceiling),
                       radius=10, segments=6)
        _boolean(chamber, opening, "UNION")
        _boolean(shell, chamber)
    else:
        cavity = _box(api, f"WorldArchitecture_{name}_CavityCutter",
                      (left, right, front - 40, rear, floor, ceiling), radius=11, segments=6)
        _boolean(shell, cavity)


def _paint_shell(api, shell, rooms):
    # A shared floor and exterior terrace can be one Boolean polygon. Split
    # that plane at the chamber bounds before assigning either surface's paint.
    mesh=bmesh.new()
    mesh.from_mesh(shell.data)
    for room in rooms.values():
        for axis, coordinate in [(0,value) for value in room["x"]]+[(1,value) for value in room["y"]]:
            floors=[face for face in mesh.faces if abs(face.calc_center_median().z-room["floorZ"])<.01 and face.normal.z>.99]
            if not floors:continue
            edges={edge for face in floors for edge in face.edges}
            vertices={vertex for edge in edges for vertex in edge.verts}
            origin=Vector((0,0,0));origin[axis]=coordinate
            normal=Vector((0,0,0));normal[axis]=1
            bmesh.ops.bisect_plane(mesh,geom=[*vertices,*edges,*floors],plane_co=origin,plane_no=normal,dist=.00001,clear_inner=False,clear_outer=False)
    mesh.to_mesh(shell.data)
    mesh.free()
    shell.data.update()
    palette = ["blue", "cream", "gold", "pink", "ink"]
    shell.data.materials.clear()
    for fill in palette:
        shell.data.materials.append(api.material(fill))

    def classify(point, normal):
        for name, room in rooms.items():
            left, right = room["x"]
            front, rear = room["y"]
            floor, ceiling = room["floorZ"], room["ceilingZ"]
            if abs(point.y-front)<.1 and normal.y<-.5:
                storey=room["storey"]
                if floor-.1<=point.z<=ceiling+.1:
                    fill="blue" if storey=="Gaming" and point.x>227 else "cream"
                    return storey+" front facade",fill
            if (left - .1 <= point.x <= right + .1 and front - .1 <= point.y <= rear + .1
                    and floor - .1 <= point.z <= ceiling + .1):
                if abs(point.z - floor) < .1 and normal.z > .5:
                    return name + " floor", room["floorFill"]
                if abs(point.z - ceiling) < .1 and normal.z < -.5:
                    return name + " ceiling", "cream"
                if abs(point.y - rear) < .1 and normal.y < -.5:
                    return name + " rear wall", room["rearFill"]
                return name + " inner wall and fillet", "gold"
        for name, storey in STOREYS.items():
            if storey["bottom"] - .1 <= point.z <= storey["top"] + .1:
                if normal.z > .5 or abs(point.z - storey["top"]) < 20.1:
                    return name + " deck", "cream"
                if normal.y < -.5:
                    fill = "blue" if name == "Gaming" and point.x > 227 else "cream"
                    return name + " front facade", fill
                return name + " exterior", "blue"
        return "Base underside", "blue"

    for polygon in shell.data.polygons:
        _, fill = classify(shell.matrix_world @ polygon.center, polygon.normal)
        polygon.material_index = palette.index(fill)
    _surface_groups(shell, classify)


def _side_port(api, shell, name, side, half_width, y, z, radius, room, center_x=0):
    x = center_x + side * half_width
    axis = (1, 0, 0)
    cutter = _cylinder(api, name + "_BoreCutter", (x - side * 10, y, z), radius, 46, axis)
    _boolean(shell, cutter)
    outside = _torus(api, name + "_OuterRim", (x + side * .5, y, z), radius + 1, 3, axis)
    inside = _torus(api, name + "_InnerRim", (x - side * 20.5, y, z), radius + 1, 2.5, axis)
    glass = _cylinder(api, name + "_Glass", (x - side * 10, y, z), radius + .35, 3, axis)
    for obj in (outside, inside, glass):
        obj["mountedTo"] = shell.name
        obj["room"] = room
        _surface_groups(obj)


def _front_port(api, shell):
    name = "WorldArchitecture_RecordingFrontPorthole"
    spec = GEOMETRY["frontPort"]
    radius = spec["r"]
    center = (spec["x"], spec["y"] + 11.5, spec["z"])
    cutter = _cylinder(api, name + "_BoreCutter", center, radius, 50, (0, 1, 0))
    _boolean(shell, cutter)
    rim = _torus(api, name + "_Rim", (spec["x"], spec["y"], spec["z"]), radius + 1, 3, (0, 1, 0))
    glass = _cylinder(api, name + "_Glass", center, radius + .35, 3, (0, 1, 0))
    for obj in (rim, glass):
        obj["mountedTo"] = shell.name
        _surface_groups(obj)


def _vent(api, shell):
    name = "WorldArchitecture_GamingServiceVent"
    spec = GEOMETRY["vent"]
    x0, x1 = spec["x"]
    z0, z1 = spec["z"]
    y = spec["y"]
    recess = _box(api, name + "_RecessCutter", (x0, x1, y - 5, y + 7, z0, z1), radius=4)
    _boolean(shell, recess)
    housing = _box(api, name + "_Housing", (x0 - 3, x1 + 3, y - 3, y + 10, z0 - 3, z1 + 3), "cream", 5)
    aperture = _box(api, name + "_OpeningCutter", (x0 + 4, x1 - 4, y - 11, y + 6, z0 + 3, z1 - 3), radius=3)
    _boolean(housing, aperture)
    housing["mountedTo"] = shell.name
    _surface_groups(housing)
    count = 9
    pitch = (z1 - z0 - 24) / count
    for index in range(count):
        z = z0 + 12 + index * pitch
        slat = _box(api, name + f"_Louver{index + 1:02}", (x0 + 2, x1 - 2, y, y + 7, z, z + pitch * .4),
                    "blue", 1.7)
        slat["mountedTo"] = housing.name
        _surface_groups(slat)


def build_world_architecture(api):
    """Build the fixed architecture and return the usable room bounds in world units."""
    rooms = _room_bounds()
    storeys = GEOMETRY["storeys"]

    def bounds(storey):
        return (*storey["x"], *storey["y"], *storey["z"])

    shell = _box(api, "WorldArchitecture_BuildingShell", bounds(storeys["Ground"]), radius=CORNER_RADIUS, segments=8)
    for name, storey in storeys.items():
        if name == "Ground":
            continue
        x0, x1, y0, y1, z0, z1 = bounds(storey)
        # Overlap the storey below by one wall so the union is weld-tight.
        solid = _box(api, f"WorldArchitecture_{name}OuterSolid", (x0, x1, y0, y1, z0 - WALL, z1),
                     radius=CORNER_RADIUS, segments=8)
        _boolean(shell, solid, "UNION")
    for name, room in rooms.items():
        _carve_room(api, shell, name, room)
    for port in GEOMETRY["ports"]:
        storey = storeys[port["storey"]]
        half_width = (storey["x"][1] - storey["x"][0]) / 2
        center_x = (storey["x"][0] + storey["x"][1]) / 2
        _side_port(api, shell, "WorldArchitecture_" + port["name"], port["side"], half_width,
                   port["y"], port["z"], port["r"], port["storey"], center_x)
    _front_port(api, shell)
    _vent(api, shell)
    _paint_shell(api, shell, rooms)
    shell["construction"] = "Unioned stepped solids from the painting fit, with bounded room cavities."

    plinth_spec = GEOMETRY["plinth"]
    px0, px1 = plinth_spec["x"]
    py0, py1 = plinth_spec["y"]
    pz0, pz1 = plinth_spec["z"]
    plinth = _box(api, "WorldArchitecture_BasePlinth", (px0, px1, py0, py1, pz0, pz1 + .5), "blue", 6)
    _surface_groups(plinth)
    foot_height = plinth_spec["footHeight"]
    for index, (x, y) in enumerate(GEOMETRY["feet"]):
        x = min(max(x, px0 + 12), px1 - 12)
        foot = _box(api, f"WorldArchitecture_Foot{index + 1:02}",
                    (x - 11, x + 11, y - 13, y + 13, 0, foot_height + .5), "blue", 2)
        foot["mountedTo"] = plinth.name
        _surface_groups(foot)
    shell["roomBounds"] = json.dumps(rooms)
    return rooms
