"""Owned artwork coordinates for the world-coordinate observatory parts."""

import json
import math

import bpy
from mathutils import Matrix, Vector

from world import AWAY, project
from world_observatory import (
    APERTURE_INNER,
    APERTURE_OUTER,
    APERTURE_Z,
    CENTER,
    COLLAR_TOP,
    OUTER_RADIUS,
    _profile_boundary,
    _shell_point,
)


SOURCE_CENTER = Vector((769, 143))
SOURCE_RIGHT = Vector((76, 22))
SOURCE_UP = Vector((-28, -82))


def _pixel(position):
    return project(position).xy


def _bbox(objects):
    points = [_pixel(obj.matrix_world @ vertex.co) for obj in objects for vertex in obj.data.vertices]
    return (min(point.x for point in points), min(point.y for point in points),
            max(point.x for point in points), max(point.y for point in points))


def _fit_mapper(objects, target):
    x0, y0, x1, y1 = _bbox(objects)
    left, top, right, bottom = target
    width, height = max(x1 - x0, .001), max(y1 - y0, .001)

    def mapper(position):
        point = _pixel(position)
        return Vector((left + (point.x - x0) / width * (right - left),
                       top + (point.y - y0) / height * (bottom - top)))

    return mapper


def _source_inside(point):
    x, y = point
    height = 239 + (x - 729) / 28 - y
    cap = max(0, height - 64) / 136
    radius = 140 * math.sqrt(max(0, 1 - cap * cap))
    return 0 <= height <= 200 and abs(x - 729) <= radius


def _source_boundary(direction):
    low, high = 0.0, 500.0
    for _ in range(42):
        distance = (low + high) * .5
        if _source_inside(SOURCE_CENTER + direction * distance):
            low = distance
        else:
            high = distance
    return SOURCE_CENTER + direction * low


def _rim(position):
    return SOURCE_CENTER + SOURCE_RIGHT * ((position.x - CENTER.x) / APERTURE_OUTER) + \
        SOURCE_UP * ((position.z - APERTURE_Z) / APERTURE_OUTER)


def _exterior_front(position):
    direction = Vector((position.x - CENTER.x, position.z - APERTURE_Z))
    distance = direction.length
    if distance < .00001:
        return SOURCE_CENTER.copy()
    direction /= distance
    boundary = Vector(_profile_boundary((CENTER.x, APERTURE_Z), direction, OUTER_RADIUS, COLLAR_TOP))
    world_radius = (boundary - Vector((CENTER.x, APERTURE_Z))).length
    fraction = max(0, min(1, (distance - APERTURE_OUTER) / max(.001, world_radius - APERTURE_OUTER)))
    source_start = SOURCE_CENTER + SOURCE_RIGHT * direction.x + SOURCE_UP * direction.y
    source_end = _source_boundary((source_start - SOURCE_CENTER).normalized())
    return source_start.lerp(source_end, fraction)


def _rear_body(position):
    return Vector((890 - (position.x - CENTER.x) * 260 / 280,
                   271 - (position.z - COLLAR_TOP) * 178 / 190))


def _rear_collar(position):
    return Vector((891 - (position.x - CENTER.x) * 281 / 300,
                   309 - (position.z - 690) * 41 / 25))


def _top_collar(position):
    return Vector((571 + (position.x - CENTER.x) * .905,
                   365 - (position.y - CENTER.y) * .905))


def _top_crown(position):
    return Vector((571 + (position.x - CENTER.x), 347 - (position.y - CENTER.y)))


def _affine_mapper(world_anchors, source_anchors):
    projected = [_pixel(Vector(point)) for point in world_anchors]
    source = [Vector(point) for point in source_anchors]
    basis = Matrix(((projected[1].x - projected[0].x, projected[2].x - projected[0].x),
                    (projected[1].y - projected[0].y, projected[2].y - projected[0].y))).inverted()

    def mapper(position):
        coordinates = basis @ (_pixel(position) - projected[0])
        return source[0] + (source[1] - source[0]) * coordinates.x + (source[2] - source[0]) * coordinates.y

    return mapper


def _leg_mapper(index):
    world_start = _pixel(Vector((352, 151, 777)))
    world_end = _pixel(Vector(((327, 125), (375, 133), (354, 190))[index] + (730,)))
    source_start = Vector((774, 174))
    source_end = Vector(((751, 202), (780, 210), (799, 199))[index])
    world_delta, source_delta = world_end - world_start, source_end - source_start
    world_normal = Vector((-world_delta.y, world_delta.x)).normalized()
    source_normal = Vector((-source_delta.y, source_delta.x)).normalized()

    def mapper(position):
        delta = _pixel(position) - world_start
        along = delta.dot(world_delta) / world_delta.length_squared
        across = delta.dot(world_normal) * .8
        return source_start + source_delta * along + source_normal * across

    return mapper


def _existing_groups(obj):
    groups = json.loads(obj.get("surfaceGroups", "{}"))
    return groups or {"Surface": {"faces": list(range(len(obj.data.polygons))), "fill": obj.get("sourceFill", "cream")}}


def _paint_object(obj, choose):
    mesh = obj.data
    uv = mesh.uv_layers.get("PaintUV") or mesh.uv_layers.new(name="PaintUV")
    depth = mesh.attributes.get("PaintDepth") or mesh.attributes.new(name="PaintDepth", type="FLOAT", domain="CORNER")
    groups = {}
    for label, group in _existing_groups(obj).items():
        label = label.split(" / ")[0]
        for index in group["faces"]:
            polygon = mesh.polygons[index]
            mapper, view, fill, source_depth = choose(label, polygon, group["fill"])
            key = label + " / " + view + " / " + fill
            entry = groups.setdefault(key, {"faces": [], "fill": fill, "view": view})
            entry["faces"].append(index)
            for loop_index in polygon.loop_indices:
                position = obj.matrix_world @ mesh.vertices[mesh.loops[loop_index].vertex_index].co
                point = mapper(position)
                uv.data[loop_index].uv = (point.x / 1536, 1 - point.y / 1024)
                depth.data[loop_index].value = source_depth + project(position).z * .01
    obj["surfaceGroups"] = json.dumps(groups)
    obj["authoredPaintUV"] = True


def _constant(fill):
    return lambda _position: Vector((20, 20))


def paint_world_observatory(api):
    """Freeze source coordinates per physical face without changing geometry."""
    objects = [obj for obj in api.collection.all_objects if obj.type == "MESH" and obj.name.startswith("WorldObservatory_")]
    if not objects:
        return
    named = {obj.name.removeprefix("WorldObservatory_"): obj for obj in objects}
    body = named["ContinuousDomeShell"]
    body_projection = _fit_mapper([body], (589, 39, 870, 242))
    collar_parts = [obj for name, obj in named.items() if name.startswith(("BaseCollar", "CollarPanelSeam", "CollarFastener"))]
    collar_projection = _fit_mapper(collar_parts, (578, 229, 878, 278))
    barrel_projection = _affine_mapper(
        ((307, 164, 836), (393, 136, 790), (352, 151, 777)),
        ((735, 121), (812, 160), (774, 174)),
    )
    chamber_projection = _affine_mapper(
        (_shell_point(CENTER.x, APERTURE_Z, OUTER_RADIUS),
         _shell_point(CENTER.x + APERTURE_INNER, APERTURE_Z, OUTER_RADIUS),
         _shell_point(CENTER.x, APERTURE_Z + APERTURE_INNER, OUTER_RADIUS)),
        (SOURCE_CENTER,
         SOURCE_CENTER + SOURCE_RIGHT * (APERTURE_INNER / APERTURE_OUTER),
         SOURCE_CENTER + SOURCE_UP * (APERTURE_INNER / APERTURE_OUTER)),
    )
    simple_regions = {
        "AntennaPlinth": (497, 253, 585, 286),
        "AntennaRaisedFoot": (525, 237, 568, 269),
        "AntennaColumn": (537, 196, 559, 248),
        "AntennaAerial": (547, 173, 552, 203),
        "AntennaTip": (547, 172, 551, 176),
        "Chimney": (876, 198, 915, 267),
        "CrownCap": (694, 29, 775, 50),
        "ServicePanel00": (627, 189, 660, 233),
        "ServicePanel02": (793, 229, 837, 268),
        "ServicePanel03": (950, 229, 991, 268),
    }
    simple_mappers = {name: _fit_mapper([named[name]], target) for name, target in simple_regions.items() if name in named}

    for name, obj in named.items():
        if name == "ContinuousDomeShell":
            def choose(label, polygon, fill):
                if label == "Exterior front":
                    return _exterior_front, "artwork", "cream", 50
                if label == "Exterior rear":
                    if polygon.normal.dot(-AWAY) > .08:
                        return body_projection, "observatory-shell", "cream", 50
                    return _rear_body, "view-rear", "cream", 50
                if label == "Raised optical rim":
                    return _rim, "observatory-rim", "cream", 0
                if label == "Interior rear":
                    return chamber_projection, "observatory-stars", "ink", 100
                return _constant(fill), "swatch", fill, 100
        elif name.startswith(("DomePanelSeam", "HorizontalPanelSeam")):
            def choose(_label, polygon, _fill):
                position = obj.matrix_world @ polygon.center
                if position.y <= CENTER.y:
                    return _exterior_front, "artwork", "cream", 40
                if polygon.normal.dot(-AWAY) > .08:
                    return body_projection, "observatory-shell", "cream", 40
                return _rear_body, "view-rear", "cream", 40
        elif name.startswith(("BaseCollar", "CollarPanelSeam", "CollarFastener")):
            def choose(_label, polygon, _fill):
                position = obj.matrix_world @ polygon.center
                source_depth = 10 if name.startswith("CollarFastener") else 40 if name.startswith("CollarPanelSeam") else 50
                if name == "BaseCollar" and polygon.normal.z < -.5:
                    return _constant("blue"), "swatch", "blue", source_depth
                if name == "BaseCollar" and polygon.normal.z > .5:
                    return _top_collar, "view-top", "blue", source_depth
                if position.y > CENTER.y and polygon.normal.dot(-AWAY) < .08:
                    return _rear_collar, "view-rear", "blue", source_depth
                return collar_projection, "artwork", "blue", source_depth
        elif name.startswith("RimRivet"):
            def choose(_label, _polygon, _fill):
                return _rim, "observatory-rim", "cream", -2
        elif name.startswith(("OpticalBarrel", "BarrelBand", "TelescopeCradle", "TripodHead")):
            def choose(_label, _polygon, fill):
                return barrel_projection, "artwork", fill, 20
        elif name.startswith("TripodLeg"):
            mapper = _leg_mapper(int(name[-2:]))

            def choose(_label, _polygon, fill):
                return mapper, "artwork", fill, 20
        elif name.startswith("TripodFoot"):
            center = ((751, 202), (780, 210), (799, 199))[int(name[-2:])]
            mapper = _fit_mapper([obj], (center[0] - 4, center[1] - 2, center[0] + 4, center[1] + 2))

            def choose(_label, _polygon, fill):
                return mapper, "artwork", fill, 19
        elif name in simple_mappers:
            mapper = simple_mappers[name]

            def choose(_label, polygon, fill):
                if name == "CrownCap" and polygon.normal.z > .5:
                    return _top_crown, "view-top", fill, 10
                view = "view-rear" if name in ("ServicePanel02", "ServicePanel03") else "artwork"
                return mapper, view, fill, 15
        else:
            def choose(_label, _polygon, fill):
                return _constant(fill), "swatch", fill, 100
        _paint_object(obj, choose)
