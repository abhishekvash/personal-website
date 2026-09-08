"""An upright ceramic planter and seated bonsai, with source paint retained."""

import math
import heapq
import json

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from tree import build_tree, _flower_and_bark_masks
from world import AWAY, GEOMETRY, RIGHT, UP, legacy_to_world, project, unproject
from world_paint import paint_source_positions


BASE_SOURCE = (1309, 792)
_PLANTER = GEOMETRY["planter"]
_RADIAL = _PLANTER["r"] / 165
_RADIAL_BASE = _PLANTER.get("rBase", _PLANTER["r"]) / 165
_VERTICAL = _PLANTER["h"] / 152
SOIL_Z = 142 * _VERTICAL
LIP_Z = 152 * _VERTICAL
SOIL_RADIUS = 153 * _RADIAL
SEGMENTS = 96
RIGHT_GROUND = Vector((RIGHT.x, RIGHT.y, 0)).normalized()
FRONT_GROUND = -Vector((AWAY.x, AWAY.y, 0)).normalized()


def _planter_center():
    if AWAY.z >= -.01:
        raise ValueError("The world camera must look downward toward positive world depth.")
    planter = GEOMETRY["planter"]
    center = Vector((planter["x"], planter["y"], 0))
    return center, project(center).z - 90


def _radial(center, angle, radius, height):
    point = center + radius * (RIGHT_GROUND * math.cos(angle) + FRONT_GROUND * math.sin(angle))
    point.z = height
    return point


def _normals(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(mesh, faces=list(mesh.faces))
    if mesh.calc_volume(signed=True) < 0:
        bmesh.ops.reverse_faces(mesh, faces=list(mesh.faces))
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()


def _upright_vessel(obj, center):
    # The broad side wall is a vertical cylinder. The foot and mouth retain
    # rounded transitions, while every circumferential ring remains level.
    def taper(radius, height):
        # Blend from the painted base radius to the painted rim radius.
        t = min(1.0, max(0.0, height / 150))
        return radius * (_RADIAL_BASE * (1 - t) + _RADIAL * t)

    profile = tuple((taper(radius, height), height * _VERTICAL) for radius, height in
                    ((153, 0), (165, 3), (165, 129), (170, 150), (168, 152), (154, 152), (152, 142), (149, 12)))
    if len(obj.data.vertices) != len(profile) * SEGMENTS:
        raise ValueError("The source planter topology changed; update the world profile.")
    for ring, (radius, height) in enumerate(profile):
        for index in range(SEGMENTS):
            obj.data.vertices[ring * SEGMENTS + index].co = _radial(center, index * math.tau / SEGMENTS, radius, height)
    obj["planterCenter"] = list(center)
    obj["planterAxis"] = [0, 0, 1]
    obj["groundZ"] = 0
    obj["soilZ"] = SOIL_Z
    obj["treeRole"] = "upright planter"
    _normals(obj)
    for polygon in obj.data.polygons[-2:]:
        polygon.use_smooth = False


def _level_soil(obj, center):
    if len(obj.data.vertices) != (SEGMENTS + 1) * 2:
        raise ValueError("The source soil topology changed; update the world soil volume.")
    for offset, height, radius in ((0, SOIL_Z, SOIL_RADIUS), (SEGMENTS + 1, 12 * _VERTICAL, 150 * _RADIAL)):
        obj.data.vertices[offset].co = center + Vector((0, 0, height))
        for index in range(SEGMENTS):
            obj.data.vertices[offset + index + 1].co = _radial(center, index * math.tau / SEGMENTS, radius, height)
    obj["treeRole"] = "level soil volume"
    obj["soilZ"] = SOIL_Z
    _normals(obj)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False


def _mounted_inlay(obj, center):
    rings, sides = 48, 10
    if len(obj.data.vertices) != rings * sides:
        raise ValueError("The source inlay topology changed; update the world fitting.")
    radius, fitting_radius = 165 * _RADIAL, 20.5
    horizontal = 1180 - BASE_SOURCE[0]
    angle = math.acos(horizontal / radius)
    surface = _radial(center, angle, radius, 0)
    height = (project(surface).y - 707) / UP.z
    points = []
    radial_normals = []
    for index in range(rings):
        phi = index * math.tau / rings
        local_angle = angle - fitting_radius / radius * math.cos(phi)
        points.append(_radial(center, local_angle, radius + .8, height - fitting_radius * math.sin(phi)))
        radial_normals.append(RIGHT_GROUND * math.cos(local_angle) + FRONT_GROUND * math.sin(local_angle))
    for index, point in enumerate(points):
        tangent = (points[(index + 1) % rings] - points[index - 1]).normalized()
        normal = radial_normals[index]
        second = tangent.cross(normal).normalized()
        for side in range(sides):
            phi = side * math.tau / sides
            obj.data.vertices[index * sides + side].co = point + 2.2 * (normal * math.cos(phi) + second * math.sin(phi))
    obj["treeRole"] = "mounted planter inlay"
    _normals(obj)


def _seat_roots(obj, center):
    sides = 16
    if len(obj.data.vertices) % sides:
        raise ValueError("Root sections must contain complete closed rings.")
    count = len(obj.data.vertices) // sides
    for ring in range(count):
        vertices = obj.data.vertices[ring * sides:(ring + 1) * sides]
        lowest = min(vertex.co.z for vertex in vertices)
        # Whole sections move together: rounded roots retain their volume.
        # The trunk junction remains unchanged; exposed lengths meet soil.
        blend = min(1, ring / max(1, count * .18))
        shift = AWAY * ((SOIL_Z - 2 - lowest) / AWAY.z * blend)
        for vertex in vertices:
            vertex.co += shift
        centroid = sum((vertex.co for vertex in vertices), Vector()) / sides
        delta = Vector((centroid.x - center.x, centroid.y - center.y, 0))
        width = max(Vector((vertex.co.x - centroid.x, vertex.co.y - centroid.y, 0)).length for vertex in vertices)
        limit = max(1, SOIL_RADIUS - width - .5)
        if delta.length > limit:
            correction = delta.normalized() * limit - delta
            for vertex in vertices:
                vertex.co += correction * blend
    obj["treeRole"] = "soil-seated root"
    _normals(obj)


def _components(mesh):
    parent = list(range(len(mesh.vertices)))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for edge in mesh.edges:
        first, second = (root(index) for index in edge.vertices)
        if first != second:
            parent[first] = second
    groups = {}
    for index in range(len(parent)):
        groups.setdefault(root(index), []).append(index)
    return groups.values()


def _seat_petals(obj, center):
    for indices in _components(obj.data):
        vertices = [obj.data.vertices[index] for index in indices]
        lowest = min(vertex.co.z for vertex in vertices)
        shift = AWAY * ((SOIL_Z + .12 - lowest) / AWAY.z)
        for vertex in vertices:
            vertex.co += shift
        centroid = sum((vertex.co for vertex in vertices), Vector()) / len(vertices)
        delta = Vector((centroid.x - center.x, centroid.y - center.y, 0))
        width = max(Vector((vertex.co.x - centroid.x, vertex.co.y - centroid.y, 0)).length for vertex in vertices)
        limit = max(1, SOIL_RADIUS - width - .5)
        if delta.length > limit:
            correction = delta.normalized() * limit - delta
            for vertex in vertices:
                vertex.co += correction
    obj["treeRole"] = "soil-seated petals"
    obj.data.update()


def _join_left_twig(objects):
    child = next(obj for obj in objects if "twisting branch 13" in obj.name)
    parent = next(obj for obj in objects if "twisting branch 04" in obj.name)
    parent.data.calc_loop_triangles()
    tree = BVHTree.FromPolygons([vertex.co for vertex in parent.data.vertices],
                               [tuple(triangle.vertices) for triangle in parent.data.loop_triangles],
                               all_triangles=True)
    center = sum((vertex.co for vertex in child.data.vertices[:16]), Vector()) / 16
    point, normal, _, distance = tree.find_nearest(center)
    if distance <= 3:
        return
    shift = point - normal * 3 - center
    # The earlier silhouette fit left this twig's first cap outside its fork.
    # Embed that cap, blending the correction into the existing closed tube.
    sections = min(8, len(child.data.vertices) // 16)
    for ring in range(sections):
        weight = (1 - ring / sections) ** 2
        for vertex in child.data.vertices[ring * 16:(ring + 1) * 16]:
            vertex.co += shift * weight
    _normals(child)


def _wood_surface(branches):
    vertices, faces = [], []
    for obj in branches:
        offset = len(vertices)
        vertices.extend(vertex.co.copy() for vertex in obj.data.vertices)
        faces.extend(tuple(offset + index for index in face.vertices) for face in obj.data.polygons)
    return vertices, faces, BVHTree.FromPolygons(vertices, faces)


def _canopy_membership(boxes, wood_projection):
    """Separate airborne source petals from the connected flowering crown."""
    parent = list(range(len(boxes)))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    near_wood = []
    for index, box in enumerate(boxes):
        gap = np.maximum(np.maximum(box[:2] - boxes[:, 2:], boxes[:, :2] - box[2:]), 0)
        for other in np.flatnonzero(np.sum(gap * gap, axis=1) <= 25 ** 2):
            first, second = root(index), root(int(other))
            if first != second:
                parent[first] = second
        wood_gap = np.maximum(np.maximum(box[:2] - wood_projection[:, :2],
                                        wood_projection[:, :2] - box[2:]), 0)
        near_wood.append(float(np.min(np.sum(wood_gap * wood_gap, axis=1))) <= 25 ** 2)
    rooted = {root(index) for index, close in enumerate(near_wood) if close}
    return [root(index) in rooted for index in range(len(boxes))]


def _spread_blossoms(canopy, wood_vertices, wood_faces):
    """Distribute closed flowers in camera depth without moving their artwork."""
    mesh = canopy.data
    components = list(_components(mesh))
    source = mesh.attributes["SourcePosition"]
    before = np.asarray([tuple(vertex.co) for vertex in mesh.vertices])
    direction = np.asarray(AWAY)
    wood_projection = np.asarray([tuple(project(point)) for point in wood_vertices])
    wood_depth = np.asarray([point.dot(AWAY) for point in wood_vertices])
    center_depth = float(np.median(wood_depth))
    boxes = np.asarray([[min(source.data[i].vector.x for i in indices),
                         min(source.data[i].vector.y for i in indices),
                         max(source.data[i].vector.x for i in indices),
                         max(source.data[i].vector.y for i in indices)] for indices in components])
    attached = _canopy_membership(boxes, wood_projection)
    # Conservative projected bounds include wood crossing a flower's interior,
    # even when that crossing misses every existing flower vertex.
    wood_front = np.full((1024, 1536), math.inf)
    for face in wood_faces:
        points = wood_projection[list(face)]
        x0, y0 = np.floor(points[:, :2].min(axis=0)).astype(int)
        x1, y1 = np.ceil(points[:, :2].max(axis=0)).astype(int) + 1
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(1536, x1), min(1024, y1)
        if x1 > x0 and y1 > y0:
            patch = wood_front[y0:y1, x0:x1]
            np.minimum(patch, float(wood_depth[list(face)].min()), out=patch)
    membership = np.empty(len(mesh.vertices), dtype=np.int32)
    for index, indices in enumerate(components):
        membership[indices] = index

    clamped = 0
    for index, indices in enumerate(components):
        current = float(np.mean(before[indices] @ direction))
        target = center_depth + (((index + 1) * .618033988749895) % 1 - .5) * 192
        shift = target - current
        x0, y0 = np.floor(boxes[index, :2]).astype(int)
        x1, y1 = np.ceil(boxes[index, 2:]).astype(int) + 1
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(1536, x1), min(1024, y1)
        front_depth = float(wood_front[y0:y1, x0:x1].min()) if x1 > x0 and y1 > y0 else math.inf
        limit = front_depth - float(np.max(before[indices] @ direction)) - 5
        if shift > limit:
            shift = limit
            clamped += 1
        for vertex_index in indices:
            mesh.vertices[vertex_index].co += AWAY * shift
    mesh.update()

    anchors, nodes = [], []
    mesh.calc_loop_triangles()
    rear_triangles = [[] for _ in components]
    for triangle in mesh.loop_triangles:
        if triangle.normal.dot(AWAY) > .5:
            rear_triangles[int(membership[triangle.vertices[0]])].append(triangle)
    for component, indices in enumerate(components):
        if not attached[component]:
            continue
        center = sum((mesh.vertices[index].co for index in indices), Vector()) / len(indices)
        rear = rear_triangles[component]
        if not rear:
            raise ValueError("A blossom component has no closed rear mounting surface")
        candidates = [(sum((mesh.vertices[index].co for index in triangle.vertices), Vector()) / 3,
                       triangle.normal.copy()) for triangle in rear]
        point, normal = min(candidates, key=lambda pair: ((pair[0] - center).dot(RIGHT) ** 2
                                                        + (pair[0] - center).dot(UP) ** 2))
        anchors.append(point - normal * .45)
        nodes.append(point + AWAY * 2.4)
    after = np.asarray([tuple(vertex.co) for vertex in mesh.vertices])
    movement = after - before
    projection_error = np.column_stack((movement @ np.asarray(RIGHT), movement @ np.asarray(UP)))
    depths = after @ direction
    canopy["depthSpread"] = json.dumps({
        "components": len(components), "depthMin": float(depths.min()), "depthMax": float(depths.max()),
        "attachedComponents": sum(attached), "ambientComponents": len(attached) - sum(attached),
        "woodOcclusionClamps": clamped,
        "maxHomeProjectionError": float(np.linalg.norm(projection_error, axis=1).max()),
    })
    canopy["ambientComponentIndices"] = [index for index, state in enumerate(attached) if not state]
    canopy["supportedComponentIndices"] = [index for index, state in enumerate(attached) if state]
    return components, anchors, nodes


def _twig_forest(api, nodes, wood):
    """Find short connected branchlets, favoring paths underneath existing ink."""
    flowers, bark = _flower_and_bark_masks(api.pixels)
    ink = flowers | bark
    positions = np.asarray([tuple(point) for point in nodes])
    projected = np.asarray([tuple(project(point)[:2]) for point in nodes])
    roots = [wood.find_nearest(point) for point in nodes]
    count = len(nodes)
    adjacency = [[] for _ in nodes]

    def cost(first, second, length):
        span = float(np.linalg.norm(second - first))
        samples = max(2, min(90, math.ceil(span / 2) + 1))
        points = first + np.linspace(0, 1, samples)[:, None] * (second - first)
        xx = np.rint(points[:, 0]).astype(int) - 930
        yy = np.rint(points[:, 1]).astype(int)
        valid = (xx >= 0) & (xx < ink.shape[1]) & (yy >= 0) & (yy < ink.shape[0])
        covered = np.zeros(samples, dtype=bool)
        covered[valid] = ink[yy[valid], xx[valid]]
        return length + span * (1 - covered.mean()) * 6

    edges = set()
    neighbors = min(18, count - 1)
    for index in range(count):
        distance = np.sum((positions - positions[index]) ** 2, axis=1)
        for other in np.argpartition(distance, neighbors)[:neighbors + 1]:
            other = int(other)
            if index == other:
                continue
            pair = (min(index, other), max(index, other))
            if pair in edges:
                continue
            edges.add(pair)
            weight = cost(projected[index], projected[other], math.sqrt(float(distance[other])))
            adjacency[index].append((other, weight))
            adjacency[other].append((index, weight))
    best = [cost(projected[index], np.asarray(project(root[0])[:2]), root[3])
            for index, root in enumerate(roots)]
    parents = [-1] * count
    pending = [(weight, index) for index, weight in enumerate(best)]
    heapq.heapify(pending)
    connected = set()
    order = []
    while pending:
        weight, index = heapq.heappop(pending)
        if index in connected or weight > best[index]:
            continue
        connected.add(index)
        order.append(index)
        for other, candidate in adjacency[index]:
            if other not in connected and candidate < best[other]:
                best[other] = candidate
                parents[other] = index
                heapq.heappush(pending, (candidate, other))
    if len(order) != count:
        raise ValueError("The blossom support forest did not reach every flower")
    descendants = np.ones(count, dtype=int)
    for index in reversed(order):
        if parents[index] >= 0:
            descendants[parents[index]] += descendants[index]
    return parents, roots, descendants


def _supporting_twigs(api, anchors, nodes, parents, roots, descendants):
    vertices, faces = [], []

    def tube(start, end, first_radius, last_radius, bend=0):
        delta = end - start
        length = delta.length
        if length < .01:
            raise ValueError("A blossom supporting twig has collapsed")
        sections = max(2, math.ceil(length / 7) + 1)
        sides = 8
        offset = len(vertices)
        reference = UP if abs(delta.normalized().dot(RIGHT)) > .8 else RIGHT
        for section in range(sections):
            fraction = section / (sections - 1)
            center = start.lerp(end, fraction) + AWAY * (math.sin(fraction * math.pi) * bend)
            tangent = (delta + AWAY * (math.pi * math.cos(fraction * math.pi) * bend)).normalized()
            normal = reference - tangent * reference.dot(tangent)
            normal.normalize()
            second = tangent.cross(normal).normalized()
            radius = first_radius * (1 - fraction) + last_radius * fraction
            for side in range(sides):
                angle = side * math.tau / sides
                vertices.append(center + radius * (normal * math.cos(angle) + second * math.sin(angle)))
        for section in range(sections - 1):
            for side in range(sides):
                a = offset + section * sides + side
                b = offset + section * sides + (side + 1) % sides
                faces.append((a, b, b + sides, a + sides))
        faces.append(tuple(offset + index for index in range(sides - 1, -1, -1)))
        faces.append(tuple(offset + (sections - 1) * sides + index for index in range(sides)))

    for index, node in enumerate(nodes):
        radius = min(.65, .35 + math.sqrt(int(descendants[index])) * .02)
        end_radius = max(.28, radius * .65)
        parent = parents[index]
        if parent < 0:
            point, normal, _, _ = roots[index]
            start = point - normal * (radius + .6)
        else:
            start = nodes[parent].copy()
        axis = (node - start).normalized()
        if parent >= 0:
            start -= axis * .7
        end = node + axis * .7
        length = (end - start).length
        tube(start, end, radius, end_radius, math.sin(index * 2.399963) * min(3, length * .03))
        # Both pieces contain the junction point inside their volume. The
        # slender stalk ends inside a real rear petal face, not its bounds.
        tube(node + AWAY * .7, anchors[index], .27, .2)
    mesh = bpy.data.meshes.new("Bonsai supporting blossom twigs")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(api.material("bark"))
    mesh.update()
    obj = bpy.data.objects.new("Bonsai • supporting blossom twigs", mesh)
    api.collection.objects.link(obj)
    for polygon in mesh.polygons:
        polygon.use_smooth = len(polygon.vertices) == 4
    obj["coordinateSpace"] = "world"
    obj["sourceFill"] = "bark"
    obj["treeRole"] = "connected blossom branchlets"
    obj["supportedBlossomComponents"] = len(nodes)
    obj["scaffoldRootConnections"] = sum(parent < 0 for parent in parents)
    paint_source_positions(obj)
    return obj


def _spread_cards(objects):
    """Spread blossom cards in camera depth, never in front of the wood that crosses them."""
    canopy = next(obj for obj in objects if "curved blossom clusters" in obj.name)
    branches = [obj for obj in objects if "twisting branch" in obj.name]
    wood_vertices, wood_faces, _ = _wood_surface(branches)
    wood_projection = np.asarray([tuple(project(point)) for point in wood_vertices])
    wood_depth = np.asarray([point.dot(AWAY) for point in wood_vertices])
    center_depth = float(np.median(wood_depth))
    wood_front = np.full((1024, 1536), math.inf)
    for face in wood_faces:
        points = wood_projection[list(face)]
        x0, y0 = np.floor(points[:, :2].min(axis=0)).astype(int)
        x1, y1 = np.ceil(points[:, :2].max(axis=0)).astype(int) + 1
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(1536, x1), min(1024, y1)
        if x1 > x0 and y1 > y0:
            patch = wood_front[y0:y1, x0:x1]
            np.minimum(patch, float(wood_depth[list(face)].min()), out=patch)
    mesh = canopy.data
    clamped = 0
    depths = []
    for index, polygon in enumerate(mesh.polygons):
        indices = list(polygon.vertices)
        current = float(np.mean([mesh.vertices[i].co.dot(AWAY) for i in indices]))
        target = center_depth + (((index + 1) * .618033988749895) % 1 - .5) * 192
        shift = target - current
        uv = np.asarray([tuple(project(mesh.vertices[i].co))[:2] for i in indices])
        x0, y0 = np.floor(uv.min(axis=0)).astype(int)
        x1, y1 = np.ceil(uv.max(axis=0)).astype(int) + 1
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(1536, x1), min(1024, y1)
        front_depth = float(wood_front[y0:y1, x0:x1].min()) if x1 > x0 and y1 > y0 else math.inf
        limit = front_depth - max(mesh.vertices[i].co.dot(AWAY) for i in indices) - 5
        if shift > limit:
            shift, clamped = limit, clamped + 1
        for i in indices:
            mesh.vertices[i].co += AWAY * shift
        depths.append(current + shift)
    mesh.update()
    canopy["depthSpread"] = json.dumps({"cards": len(mesh.polygons), "depthMin": float(min(depths)),
                                        "depthMax": float(max(depths)), "woodOcclusionClamps": clamped})
    print(f"WORLD CANOPY {len(mesh.polygons)} blossom cards / {canopy['depthSpread']}", flush=True)


def _volumetric_canopy(api, objects):
    canopy = next(obj for obj in objects if "curved blossom clusters" in obj.name)
    branches = [obj for obj in objects if "twisting branch" in obj.name]
    wood_vertices, wood_faces, wood = _wood_surface(branches)
    components, anchors, nodes = _spread_blossoms(canopy, wood_vertices, wood_faces)
    parents, roots, descendants = _twig_forest(api, nodes, wood)
    twigs = _supporting_twigs(api, anchors, nodes, parents, roots, descendants)
    canopy["supportingTwigs"] = twigs.name
    print(f"WORLD CANOPY {len(nodes)} supported blossoms / {canopy['depthSpread']}", flush=True)
    return twigs


def build_world_tree(api):
    """Return world-space bonsai objects, retaining SourcePosition and PaintUV."""
    before = set(api.collection.all_objects)
    build_tree(api)
    objects = [obj for obj in api.collection.all_objects if obj not in before and obj.type == "MESH"]
    center, depth_offset = _planter_center()
    for obj in objects:
        if obj.data.attributes.get("SourcePosition") is None:
            raise ValueError(f"Missing source paint coordinates on {obj.name}")
        paint_source_positions(obj, 300)
        legacy_to_world(obj, depth_offset)
        if "glazed ceramic planter" in obj.name:
            _upright_vessel(obj, center)
        elif "petal-covered soil" in obj.name:
            _level_soil(obj, center)
        elif "planter round inlay" in obj.name:
            _mounted_inlay(obj, center)
        elif "spreading root" in obj.name:
            _seat_roots(obj, center)
        elif "individual fallen petals" in obj.name:
            _seat_petals(obj, center)
        else:
            obj["treeRole"] = "branch" if "twisting branch" in obj.name else "curved canopy blossoms"
        obj["coordinateSpace"] = "world"
    _join_left_twig(objects)
    _spread_cards(objects)
    return objects
