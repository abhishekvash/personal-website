"""A round observatory assembled in orthogonal Blender world coordinates."""

import json
import math

import bmesh
import bpy
from mathutils import Vector

from world import GEOMETRY


_DOME = GEOMETRY["dome"]
CENTER = Vector((_DOME["x"], _DOME["y"], 0))
ROOF_Z = _DOME["roofZ"]
COLLAR_TOP = ROOF_Z + 25
SHOULDER_Z = _DOME["shoulderZ"]
OUTER_RADIUS = _DOME["r"]
INNER_RADIUS = OUTER_RADIUS - 12
FLOOR_Z = ROOF_Z + 37
APERTURE_Z = SHOULDER_Z + 45
APERTURE_OUTER = 91.5 * OUTER_RADIUS / 140
APERTURE_INNER = 75.5 * OUTER_RADIUS / 140
SEGMENTS = 128


def _mesh(api, name, vertices, faces, fill="cream", groups=None, smooth=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new("WorldObservatory_" + name, data)
    api.collection.objects.link(obj)
    data.materials.append(api.material(fill))
    obj["coordinateSpace"] = "world"
    obj["sourceFill"] = fill
    if groups:
        obj["surfaceGroups"] = json.dumps(groups)
        materials = {fill: 0}
        for group in groups.values():
            material = group["fill"]
            if material not in materials:
                materials[material] = len(data.materials)
                data.materials.append(api.material(material))
            for index in group["faces"]:
                data.polygons[index].material_index = materials[material]
    mesh = bmesh.new()
    mesh.from_mesh(data)
    bmesh.ops.recalc_face_normals(mesh, faces=list(mesh.faces))
    if mesh.calc_volume(signed=True) < 0:
        bmesh.ops.reverse_faces(mesh, faces=list(mesh.faces))
    mesh.to_mesh(data)
    mesh.free()
    for polygon in data.polygons:
        polygon.use_smooth = smooth
    return obj


class _AssemblyMesh:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.groups = {}

    def vertex(self, point):
        self.vertices.append(tuple(point))
        return len(self.vertices) - 1

    def face(self, indices, label, fill):
        indices = list(dict.fromkeys(indices))
        if len(indices) < 3:
            return
        group = self.groups.setdefault(label, {"faces": [], "fill": fill})
        group["faces"].append(len(self.faces))
        self.faces.append(tuple(indices))

    def bridge(self, first, second, label, fill):
        for index in range(len(first)):
            following = (index + 1) % len(first)
            self.face((first[index], first[following], second[following], second[index]), label, fill)

    def finish(self, api, name, fill="cream", smooth=False):
        return _mesh(api, name, self.vertices, self.faces, fill, self.groups, smooth)


def _radius_at(z, radius):
    return math.sqrt(max(0, radius * radius - max(0, z - SHOULDER_Z) ** 2))


def _inside_profile(x, z, radius, base):
    return base <= z <= SHOULDER_Z + radius and abs(x - CENTER.x) <= _radius_at(z, radius)


def _shell_point(x, z, radius, rear=False):
    projected_radius = _radius_at(z, radius)
    depth = math.sqrt(max(0, projected_radius * projected_radius - (x - CENTER.x) ** 2))
    return x, CENTER.y + depth * (1 if rear else -1), z


def _profile_boundary(origin, direction, radius, base):
    low, high = 0.0, 400.0
    for _ in range(55):
        distance = (low + high) * .5
        if _inside_profile(origin[0] + direction[0] * distance,
                           origin[1] + direction[1] * distance, radius, base):
            low = distance
        else:
            high = distance
    return origin[0] + direction[0] * low, origin[1] + direction[1] * low


def _shell_layer(builder, radius, base, opening, label, fill):
    origin = (CENTER.x, APERTURE_Z)
    directions = [(math.cos(index * math.tau / SEGMENTS), math.sin(index * math.tau / SEGMENTS))
                  for index in range(SEGMENTS)]
    boundary = [_profile_boundary(origin, direction, radius, base) for direction in directions]
    aperture = [(origin[0] + direction[0] * opening, origin[1] + direction[1] * opening)
                for direction in directions]
    if not all(_inside_profile(x, z, radius, base) for x, z in aperture):
        raise ValueError("Observatory aperture extends beyond its round shell.")
    previous = aperture_indices = None
    bands = 24
    for band in range(bands + 1):
        fraction = band / bands
        current = []
        for start, end in zip(aperture, boundary):
            x, z = (start[axis] * (1 - fraction) + end[axis] * fraction for axis in range(2))
            point = _shell_point(x, z, radius)
            if band == bands and z > base + .00001:
                point = (x, CENTER.y, z)
            current.append(builder.vertex(point))
        if previous is None:
            aperture_indices = current
        else:
            builder.bridge(previous, current, label + " front", fill)
        previous = current
    front_boundary = previous
    back_boundary = [front_boundary[index] if z > base + .00001 else
                     builder.vertex(_shell_point(x, z, radius, rear=True))
                     for index, (x, z) in enumerate(boundary)]
    center = builder.vertex(_shell_point(*origin, radius, rear=True))
    previous = None
    for band in range(1, bands + 1):
        fraction = band / bands
        current = back_boundary if band == bands else [
            builder.vertex(_shell_point(origin[0] * (1 - fraction) + x * fraction,
                                        origin[1] * (1 - fraction) + z * fraction, radius, rear=True))
            for x, z in boundary
        ]
        if previous is None:
            for index in range(SEGMENTS):
                builder.face((center, current[index], current[(index + 1) % SEGMENTS]), label + " rear", fill)
        else:
            builder.bridge(previous, current, label + " rear", fill)
        previous = current
    builder.bridge(front_boundary, back_boundary, label + " floor", fill)
    return aperture_indices, aperture


def _build_shell(api):
    builder = _AssemblyMesh()
    outer_boundary, outer = _shell_layer(builder, OUTER_RADIUS, COLLAR_TOP, APERTURE_OUTER, "Exterior", "cream")
    inner_boundary, inner = _shell_layer(builder, INNER_RADIUS, FLOOR_Z, APERTURE_INNER, "Interior", "ink")
    rim_outer, rim_inner = [], []
    for points, target in ((outer, rim_outer), (inner, rim_inner)):
        for x, z in points:
            point = Vector(_shell_point(x, z, OUTER_RADIUS))
            point.y -= 5
            target.append(builder.vertex(point))
    builder.bridge(outer_boundary, rim_outer, "Rim outer return", "cream")
    builder.bridge(rim_outer, rim_inner, "Raised optical rim", "cream")
    builder.bridge(rim_inner, inner_boundary, "Optical tunnel", "ink")
    shell = builder.finish(api, "ContinuousDomeShell", smooth=True)
    for name, group in builder.groups.items():
        if "floor" in name:
            for index in group["faces"]:
                shell.data.polygons[index].use_smooth = False
    return shell


def _lathe(api, name, origin, axis, profile, fill="blue", segment_fills=None, segments=48, end_fills=None):
    origin, axis = Vector(origin), Vector(axis).normalized()
    normal = axis.cross(Vector((0, 0, 1)))
    if normal.length < .01:
        normal = axis.cross(Vector((0, 1, 0)))
    normal.normalize()
    second = axis.cross(normal).normalized()
    builder = _AssemblyMesh()
    rings = []
    for distance, radius in profile:
        rings.append([builder.vertex(origin + axis * distance + radius *
                                     (normal * math.cos(index * math.tau / segments) +
                                      second * math.sin(index * math.tau / segments)))
                      for index in range(segments)])
    for index in range(len(rings) - 1):
        material = segment_fills[index] if segment_fills else fill
        builder.bridge(rings[index], rings[index + 1], f"Band {index + 1}", material)
    builder.face(rings[0][::-1], "First cap", end_fills[0] if end_fills else fill)
    builder.face(rings[-1], "Last cap", end_fills[1] if end_fills else fill)
    obj = builder.finish(api, name, fill, smooth=True)
    for name, group in builder.groups.items():
        if "cap" in name:
            for index in group["faces"]:
                obj.data.polygons[index].use_smooth = False
    return obj


def _tube(api, name, points, radius, fill="ink", sides=10):
    points = [Vector(point) for point in points]
    builder = _AssemblyMesh()
    rings = []
    for index, point in enumerate(points):
        direction = (points[min(index + 1, len(points) - 1)] - points[max(0, index - 1)]).normalized()
        normal = direction.cross(Vector((0, 0, 1)))
        if normal.length < .01:
            normal = direction.cross(Vector((0, 1, 0)))
        normal.normalize()
        second = direction.cross(normal).normalized()
        rings.append([builder.vertex(point + radius * (normal * math.cos(side * math.tau / sides) +
                                                       second * math.sin(side * math.tau / sides)))
                      for side in range(sides)])
        if index:
            builder.bridge(rings[-2], rings[-1], "Tube", fill)
    builder.face(rings[0][::-1], "First cap", fill)
    builder.face(rings[-1], "Last cap", fill)
    return builder.finish(api, name, fill, smooth=True)


def _box(api, name, center, size, fill="blue", bevel=1):
    center, half = Vector(center), Vector(size) * .5
    corners = [tuple(center + Vector((x * half.x, y * half.y, z * half.z)))
               for z in (-1, 1) for y in (-1, 1) for x in (-1, 1)]
    faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4),
             (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    obj = _mesh(api, name, corners, faces, fill)
    if bevel:
        modifier = obj.modifiers.new("Rounded manufactured edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    return obj


def _ball(api, name, center, radius, fill="cream"):
    center = Vector(center)
    segments, bands = 16, 8
    builder = _AssemblyMesh()
    top, bottom = builder.vertex(center + Vector((0, 0, radius))), builder.vertex(center - Vector((0, 0, radius)))
    rings = []
    for band in range(1, bands):
        elevation = math.pi * band / bands
        rings.append([builder.vertex(center + radius * Vector((math.sin(elevation) * math.cos(index * math.tau / segments),
                                                                math.sin(elevation) * math.sin(index * math.tau / segments),
                                                                math.cos(elevation)))) for index in range(segments)])
    for index in range(segments):
        following = (index + 1) % segments
        builder.face((top, rings[0][index], rings[0][following]), "Dome", fill)
        builder.face((bottom, rings[-1][following], rings[-1][index]), "Dome", fill)
    for index in range(len(rings) - 1):
        builder.bridge(rings[index], rings[index + 1], "Dome", fill)
    return builder.finish(api, name, fill, smooth=True)


def _build_collar(api):
    _lathe(api, "BaseCollar", (CENTER.x, CENTER.y, ROOF_Z), (0, 0, 1),
           [(0, 148), (1.5, 150), (23.5, 150), (25, 148)], "blue", segments=96)
    for index in range(16):
        angle = index * math.tau / 16
        x, y = CENTER.x + 150.15 * math.cos(angle), CENTER.y + 150.15 * math.sin(angle)
        _tube(api, f"CollarPanelSeam{index:02}", [(x, y, 693), (x, y, 712)], .42)
    for index, angle in enumerate((-2.18, -1.22, .89, 2.15)):
        point = (CENTER.x + 150 * math.cos(angle), CENTER.y + 150 * math.sin(angle), 702)
        _ball(api, f"CollarFastener{index:02}", point, 3.4)
    _lathe(api, "CrownCap", (CENTER.x, CENTER.y, SHOULDER_Z + OUTER_RADIUS - 2), (0, 0, 1),
           [(0, 26), (2, 31), (8, 31), (9, 29)], "blue", segments=64,
           segment_fills=["gold", "blue", "cream"])


def _build_panel_details(api):
    for index in range(12):
        angle = index * math.tau / 12
        points = []
        for step in range(61):
            z = COLLAR_TOP + 2 + step / 60 * (OUTER_RADIUS + SHOULDER_Z - COLLAR_TOP - 5)
            radius = _radius_at(z, OUTER_RADIUS) + .22
            point = (CENTER.x + radius * math.cos(angle), CENTER.y + radius * math.sin(angle), z)
            # Front seams stop at the actual optical opening and resume above it.
            in_aperture = point[1] < CENTER.y and (point[0] - CENTER.x) ** 2 + (z - APERTURE_Z) ** 2 < (APERTURE_OUTER + 2) ** 2
            if in_aperture:
                if len(points) > 1:
                    _tube(api, f"DomePanelSeam{index:02}_{step:02}", points, .38)
                points = []
            else:
                points.append(point)
        if len(points) > 1:
            _tube(api, f"DomePanelSeam{index:02}_Upper", points, .38)
    for level, z in enumerate((SHOULDER_Z, SHOULDER_Z + 69 * OUTER_RADIUS / 140)):
        radius = _radius_at(z, OUTER_RADIUS) + .22
        pending = []
        for step in range(129):
            angle = step * math.tau / 128
            point = (CENTER.x + radius * math.cos(angle), CENTER.y + radius * math.sin(angle), z)
            in_aperture = point[1] < CENTER.y and (point[0] - CENTER.x) ** 2 + (z - APERTURE_Z) ** 2 < (APERTURE_OUTER + 2) ** 2
            if in_aperture:
                if len(pending) > 1:
                    _tube(api, f"HorizontalPanelSeam{level}_{step}", pending, .38)
                pending = []
            else:
                pending.append(point)
        if len(pending) > 1:
            _tube(api, f"HorizontalPanelSeam{level}_End", pending, .38)
    for index in range(20):
        angle = round(index * SEGMENTS / 20) * math.tau / SEGMENTS
        edge_points = [Vector(_shell_point(CENTER.x + radius * math.cos(angle),
                                           APERTURE_Z + radius * math.sin(angle), OUTER_RADIUS))
                       for radius in (APERTURE_OUTER, APERTURE_INNER)]
        point = (edge_points[0] + edge_points[1]) * .5
        point.y -= 5.6
        _ball(api, f"RimRivet{index:02}", point, 1.15, "gold")
    for index, angle in enumerate((3.92, 5.50, .86, 2.28)):
        builder = _AssemblyMesh()
        rings = []
        for radius, z in ((OUTER_RADIUS - .4, FLOOR_Z), (OUTER_RADIUS + 2.6, FLOOR_Z), (OUTER_RADIUS + 2.6, FLOOR_Z + 29), (OUTER_RADIUS - .4, FLOOR_Z + 29)):
            rings.append([builder.vertex((CENTER.x + radius * math.cos(angle - .105 + step * .21 / 8),
                                           CENTER.y + radius * math.sin(angle - .105 + step * .21 / 8), z))
                          for step in range(9)])
        for ring in range(4):
            first, second = rings[ring], rings[(ring + 1) % 4]
            for step in range(8):
                builder.face((first[step], first[step + 1], second[step + 1], second[step]), "Panel", "blue")
        builder.face([ring[0] for ring in rings], "End", "blue")
        builder.face([ring[-1] for ring in rings], "End", "blue")
        builder.finish(api, f"ServicePanel{index:02}", "blue")


def _build_roof_fittings(api):
    # Positions come from the painting fit; heights are relative to the roof.
    x, y = GEOMETRY["fittings"]["antenna"]
    _box(api, "AntennaPlinth", (x, y, ROOF_Z + 7), (70, 60, 14), bevel=1.4)
    _box(api, "AntennaRaisedFoot", (x, y, ROOF_Z + 19), (40, 38, 11), bevel=1)
    _lathe(api, "AntennaColumn", (x, y, ROOF_Z + 24), (0, 0, 1),
           [(0, 12), (5, 12), (5.5, 8), (62, 8), (63.5, 6.5)], "cream", segments=32,
           segment_fills=["blue", "blue", "cream", "cream"])
    _lathe(api, "AntennaAerial", (x, y, ROOF_Z + 86), (0, 0, 1), [(0, 1.5), (58, 1.15)], "blue", segments=16)
    _ball(api, "AntennaTip", (x, y, ROOF_Z + 144), 1.8, "gold")
    x, y = GEOMETRY["fittings"]["chimney"]
    _lathe(api, "Chimney", (x, y, ROOF_Z), (0, 0, 1),
           [(0, 18), (10, 18), (11, 13), (40, 13), (41, 13), (70, 13), (70.5, 16), (73, 16)],
           "cream", segments=48,
           segment_fills=["cream", "cream", "cream", "ink", "cream", "cream", "cream"])


def _build_telescope(api):
    base = Vector((CENTER.x, CENTER.y, ROOF_Z))
    objective = base + Vector((-43, -46, 146))
    tail = base + Vector((43, -74, 100))
    axis = (tail - objective).normalized()
    length = (tail - objective).length
    _lathe(api, "OpticalBarrel", objective, axis,
           [(0, 12), (4, 12), (5, 10), (36, 10), (37, 9), (63, 9), (64, 7.5), (length, 7.5)],
           "cream", segments=48,
           segment_fills=["gold", "gold", "cream", "gold", "cream", "gold", "cream"],
           end_fills=("ink", "ink"))
    for index, distance in enumerate((5, 17, 36, 51, 64, length - 5)):
        radius = 11 if distance < 36 else 10 if distance < 64 else 8.5
        _lathe(api, f"BarrelBand{index:02}", objective + axis * (distance - 1), axis,
               [(0, radius), (2, radius)], "gold", segments=40)
    pivot = base + Vector((2, -59, 87))
    attachment = objective + axis * 53
    _tube(api, "TelescopeCradle", [pivot, attachment], 5.5, "gold", sides=16)
    _ball(api, "TripodHead", pivot, 7, "gold")
    for index, (x, y) in enumerate(((base.x - 23, base.y - 85), (base.x + 25, base.y - 77), (base.x + 4, base.y - 20))):
        _tube(api, f"TripodLeg{index:02}", [pivot, (x, y, FLOOR_Z + 3)], 3.2, "gold", sides=12)
        _lathe(api, f"TripodFoot{index:02}", (x, y, FLOOR_Z), (0, 0, 1), [(0, 5), (3, 5), (4, 3)],
               "gold", segments=20)


def build_world_observatory(api):
    """Build closed observatory parts on the flat upper roof at the fitted roof height."""
    _build_shell(api)
    _build_collar(api)
    _build_panel_details(api)
    _build_roof_fittings(api)
    _build_telescope(api)
