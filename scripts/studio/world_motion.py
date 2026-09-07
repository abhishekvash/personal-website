"""Ambient meshes mounted to the finished, orthogonal studio geometry."""

import json
import math

import bpy
from mathutils import Matrix, Vector

from motion import plume_material
from world import AWAY, RIGHT


def _points(obj):
    return [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]


def _required(name):
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "MESH" or obj.get("coordinateSpace") != "world":
        raise ValueError(f"World motion requires the adapted mesh {name}")
    return obj


def _mesh(api, name, points, faces, material, center=None):
    center = center if center is not None else sum(points, Vector()) / len(points)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([point - center for point in points], [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    api.collection.objects.link(obj)
    obj.location = center
    obj["coordinateSpace"] = "world"
    return obj


def _steam(api):
    specification = json.loads((api.root / "assets/studio/motion.json").read_text())
    shell = _required("WorldArchitecture_BuildingShell")
    room = json.loads(shell["roomBounds"])["Kitchen"]
    supports = ("Interior_Kitchen_PanFood", "Interior_Kitchen_PotLiquid")
    if len(specification) != len(supports):
        raise ValueError("The source must contain exactly the pan and pot steam crops")
    result = []
    for index, (item, support_name) in enumerate(zip(specification, supports)):
        support = _required(support_name)
        points = _points(support)
        anchor = Vector((sum(point.x for point in points) / len(points),
                         sum(point.y for point in points) / len(points),
                         max(point.z for point in points)))
        x0, y0, x1, y1 = item["bounds"]
        width = (x1 - x0) * .9
        height = min((y1 - y0) * .8, room["ceilingZ"] - anchor.z - 10)
        if height < 15:
            raise ValueError(f"No headroom for steam above {support_name}")
        vertices = []
        uv_points = []
        for row in range(7):
            t = row / 6
            center = anchor + Vector((0, 0, height * t)) + AWAY * (math.sin(t * math.pi) * 1.5)
            vertices.extend((center - RIGHT * width / 2, center + RIGHT * width / 2))
            uv_points.extend(((0, t), (1, t)))
        faces = [(row * 2, row * 2 + 1, row * 2 + 3, row * 2 + 2) for row in range(6)]
        obj = _mesh(api, item["name"], vertices, faces, plume_material(api, item["texture"]))
        uv = obj.data.uv_layers.new(name="SteamUV")
        for loop in obj.data.loops:
            uv.data[loop.index].uv = uv_points[loop.vertex_index]
        obj["motion"] = {"duration": 8 + index * 2, "phase": 0, "drift": 1.5, "rise": 3.5}
        obj["mountedTo"] = support_name
        obj["sourceCrop"] = item["bounds"]
        obj["sourceTexture"] = item["texture"]
        result.append(obj)
    return result


def _glow_material():
    material = bpy.data.materials.new("WorldScreenGlow")
    material.use_nodes = True
    material.surface_render_method = "BLENDED"
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (0, 0, 0, 1)
    shader.inputs["Emission Color"].default_value = (.94, .63, .53, 1)
    shader.inputs["Emission Strength"].default_value = 1
    shader.inputs["Alpha"].default_value = 1
    return material


def _screens(api):
    names = ("Interior_Gaming_MainMonitor_Screen", "Interior_Recording_ConsoleMonitor_Screen",
             "Interior_Workspace_LeftMonitor_Screen", "Interior_Workspace_RightMonitor_Screen")
    material = _glow_material()
    result = []
    for index, name in enumerate(names):
        screen = _required(name)
        normal_matrix = screen.matrix_world.to_3x3().inverted().transposed()
        front = [face for face in screen.data.polygons if (normal_matrix @ face.normal).y < -.5]
        if not front:
            raise ValueError(f"No outward front face on {name}")
        face = max(front, key=lambda polygon: polygon.area)
        normal = (normal_matrix @ face.normal).normalized()
        plane = screen.matrix_world @ face.center
        front = [polygon for polygon in front
                 if (normal_matrix @ polygon.normal).normalized().dot(normal) > .995
                 and abs((screen.matrix_world @ polygon.center - plane).dot(normal)) < .2]
        indices = sorted({i for polygon in front for i in polygon.vertices})
        lookup = {source: target for target, source in enumerate(indices)}
        vertices = [screen.matrix_world @ screen.data.vertices[i].co + normal * .08 for i in indices]
        faces = [tuple(lookup[i] for i in polygon.vertices) for polygon in front]
        obj = _mesh(api, f"ScreenGlow{index + 1:02}", vertices, faces, material)
        obj["motion"] = {"duration": 9 + index, "phase": index * .21}
        obj["mountedTo"] = name
        # SceneAtmosphere keeps glow invisible at the reference pose, then
        # animates from this nonzero material opacity after interaction begins.
        obj["restOpacity"] = 0
        result.append(obj)
    return result


def _petals(api):
    canopy = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"
              and "blossom clusters" in obj.name and obj.get("coordinateSpace") == "world"]
    if not canopy:
        raise ValueError("World motion requires the transformed Bonsai blossom clusters")
    points = [point for obj in canopy for point in _points(obj)]
    low = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    high = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    span = high - low
    # Closed, slightly cupped petals originate on three real canopy surfaces.
    outline = ((0, -6), (2.6, -3.8), (3.2, .5), (1.5, 4.8),
               (0, 6), (-2, 4), (-3, 0), (-2.5, -4))
    result = []
    for index, fraction in enumerate(((.2, .28, .3), (.78, .22, .35), (.46, .22, .58))):
        target = low + Vector(tuple(span[axis] * fraction[axis] for axis in range(3)))
        anchor = min(points, key=lambda point: (point - target).length_squared).copy()
        anchor -= AWAY * 3
        anchor.z -= 4
        rotation = Matrix.Rotation(index * .8 - .4, 3, "Z")
        local = [Vector((x, .25 + abs(x) * .08, z)) for x, z in outline]
        local += [Vector((x, -.25 + abs(x) * .08, z)) for x, z in outline]
        local += [Vector((0, -.5, 0)), Vector((0, -.9, 0))]
        vertices = [anchor + rotation @ point for point in local]
        faces = [(16, i, (i + 1) % 8) for i in range(8)]
        faces += [(17, (i + 1) % 8 + 8, i + 8) for i in range(8)]
        faces += [(i, i + 8, (i + 1) % 8 + 8, (i + 1) % 8) for i in range(8)]
        faces = [tuple(reversed(face)) for face in faces]
        obj = _mesh(api, f"FallingPetal{index + 1:02}", vertices, faces, api.material("pink"), anchor)
        obj["motion"] = {"duration": 16 + index * 2, "phase": index * .3, "drift": -16, "rise": -72}
        obj["restOpacity"] = 0
        obj["mountedTo"] = canopy[0].name
        result.append(obj)
    return result


def build_world_motion(api):
    """Build after interiors and bonsai; names stay separate during glTF batching."""
    existing = [obj.name for obj in bpy.context.scene.objects
                if obj.name.startswith(("Steam", "FallingPetal", "ScreenGlow"))]
    if existing:
        raise ValueError(f"World motion already exists: {', '.join(existing)}")
    return [*_steam(api), *_screens(api), *_petals(api)]
