"""Canonical solid architecture in world X (width), Y (depth), Z (height).

The front faces negative Y. No image coordinates or camera projection enter
the construction; the publishing pipeline assigns artwork and UVs afterward.
"""

import json

import bmesh
import bpy
from mathutils import Matrix, Vector


STOREYS = {
    "Ground": {"width": 700, "depth": 420, "bottom": 40, "top": 280},
    "Recording": {"width": 650, "depth": 365, "bottom": 280, "top": 475},
    "Gaming": {"width": 585, "depth": 310, "bottom": 475, "top": 690},
}


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
    return {
        "Workspace": {"x": [-330, -10], "y": [-210, 190], "floorZ": 60,
                      "ceilingZ": 260, "openingX": [-330, -10], "frontY": -210,
                      "floorFill": "gold", "rearFill": "pink", "storey": "Ground"},
        "Kitchen": {"x": [10, 330], "y": [-210, 190], "floorZ": 60,
                    "ceilingZ": 260, "openingX": [10, 330], "frontY": -210,
                    "floorFill": "gold", "rearFill": "gold", "storey": "Ground"},
        "Recording": {"x": [-305, 305], "y": [-182.5, 162.5], "floorZ": 280,
                      "ceilingZ": 455, "openingX": [-305, 215], "frontY": -182.5,
                      "floorFill": "pink", "rearFill": "pink", "storey": "Recording"},
        "Gaming": {"x": [-272.5, 272.5], "y": [-155, 135], "floorZ": 475,
                   "ceilingZ": 670, "openingX": [-172.5, 227.5], "frontY": -155,
                   "usableX": [-172.5, 272.5], "serviceBayWidth": 100,
                   "floorFill": "pink", "rearFill": "pink", "storey": "Gaming"},
    }


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


def _side_port(api, shell, name, side, half_width, y, z, radius, room):
    x = side * half_width
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
    center = (285, -171.5, 408)
    cutter = _cylinder(api, name + "_BoreCutter", center, 30, 50, (0, 1, 0))
    _boolean(shell, cutter)
    rim = _torus(api, name + "_Rim", (285, -183, 408), 31, 3, (0, 1, 0))
    glass = _cylinder(api, name + "_Glass", center, 30.35, 3, (0, 1, 0))
    for obj in (rim, glass):
        obj["mountedTo"] = shell.name
        _surface_groups(obj)


def _vent(api, shell):
    name = "WorldArchitecture_GamingServiceVent"
    bounds = (-274, -209, -160, -148, 540, 653)
    recess = _box(api, name + "_RecessCutter", bounds, radius=4)
    _boolean(shell, recess)
    housing = _box(api, name + "_Housing", (-277, -206, -158, -145, 537, 656), "cream", 5)
    aperture = _box(api, name + "_OpeningCutter", (-270, -213, -166, -149, 543, 650), radius=3)
    _boolean(housing, aperture)
    housing["mountedTo"] = shell.name
    _surface_groups(housing)
    for index in range(9):
        z = 552 + index * 10.6
        slat = _box(api, name + f"_Louver{index + 1:02}", (-272, -211, -155, -148, z, z + 4.2),
                    "blue", 1.7)
        slat["mountedTo"] = housing.name
        _surface_groups(slat)


def build_world_architecture(api):
    """Build the fixed architecture and return the usable room bounds in world units."""
    existing = set(bpy.context.scene.objects)
    rooms = _room_bounds()
    shell = _box(api, "WorldArchitecture_BuildingShell", (-350, 350, -210, 210, 40, 280), radius=7)
    middle = _box(api, "WorldArchitecture_RecordingOuterSolid", (-325, 325, -182.5, 182.5, 260, 475), radius=7)
    upper = _box(api, "WorldArchitecture_GamingOuterSolid", (-292.5, 292.5, -155, 155, 455, 690), radius=7)
    _boolean(shell, middle, "UNION")
    _boolean(shell, upper, "UNION")
    for name, room in rooms.items():
        _carve_room(api, shell, name, room)
    for room, half_width, z, radius in (("Ground", 350, 159, 37),
                                        ("Recording", 325, 371, 39),
                                        ("Gaming", 292.5, 575, 35)):
        for side, label in ((-1, "Left"), (1, "Right")):
            positions={"Ground":((-65,208),(80,159)),"Recording":((-20,426),(80,371)),"Gaming":((-15,611),(108,542))}
            y,z=positions[room][0 if side<0 else 1]
            _side_port(api, shell, f"WorldArchitecture_{room}{label}Porthole",
                       side, half_width, y, z, radius, room)
    for side, label in ((-1, "Left"), (1, "Right")):
        _side_port(api, shell, f"WorldArchitecture_Ground{label}SmallPorthole",
                   side, 350, 64 if side<0 else 92, 231 if side<0 else 221, 13, "Ground")
    _front_port(api, shell)
    _vent(api, shell)
    _paint_shell(api, shell, rooms)
    shell["construction"] = "Unioned stepped solids with shared 20-unit decks and bounded room cavities."

    plinth = _box(api, "WorldArchitecture_BasePlinth", (-370, 370, -222.5, 222.5, 20, 40.5), "blue", 8)
    _surface_groups(plinth)
    for index, (x, y) in enumerate(((-320, -181), (-107, -181), (107, -181), (320, -181),
                                    (-320, 181), (320, 181))):
        foot = _box(api, f"WorldArchitecture_Foot{index + 1:02}",
                    (x - 10, x + 10, y - 13, y + 13, 0, 20.5), "blue", 2)
        foot["mountedTo"] = plinth.name
        _surface_groups(foot)
    # The construction is centered for symmetry. Publish a corner-based world
    # frame shared by furniture, dome, and camera: ground x0..700, y0..420.
    offset = Matrix.Translation((350, 210, 0))
    for obj in set(bpy.context.scene.objects) - existing:
        if obj.type == "MESH":
            obj.data.transform(offset @ obj.matrix_world)
            obj.matrix_world = Matrix.Identity(4)
            obj.data.update()
    for room in rooms.values():
        for key in ("x", "openingX", "usableX"):
            if key in room:
                room[key] = [value + 350 for value in room[key]]
        room["y"] = [value + 210 for value in room["y"]]
        room["frontY"] += 210
    shell["roomBounds"] = json.dumps(rooms)
    return rooms
