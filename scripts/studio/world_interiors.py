"""Adapt editable furniture to orthogonal world rooms without changing artwork coordinates."""

import math

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from world import AWAY


ROOM_AXES = {
    "Gaming": {"slope": .10, "shear": .268, "rise": .218, "scale": (1.25, 1.1, 1.05)},
    "Workspace": {"slope": .11, "shear": .45, "rise": .36, "scale": (1.15, 1.1, 1.0)},
    "Kitchen": {"slope": .06, "shear": .34, "rise": .27, "scale": (1.08, 1.3, .8)},
    "Recording": {"slope": .118, "shear": .64, "rise": .65, "scale": (1.3, 1.0, 1.15)},
}


def _limits(objects):
    points = [vertex.co for obj in objects for vertex in obj.data.vertices]
    return (Vector(tuple(min(point[axis] for point in points) for axis in range(3))),
            Vector(tuple(max(point[axis] for point in points) for axis in range(3))))


def _center(obj):
    low, high = _limits([obj])
    return (low + high) / 2


def _move(objects, offset):
    for obj in objects:
        for vertex in obj.data.vertices:
            vertex.co += offset
        obj.data.update()


def _bend(obj, first, second, first_shift, second_shift):
    axis = second - first
    if axis.length_squared < 1e-8:
        raise ValueError(f"Collapsed support axis: {obj.name}")
    for vertex in obj.data.vertices:
        weight = max(0, min(1, (vertex.co - first).dot(axis) / axis.length_squared))
        vertex.co += first_shift.lerp(second_shift, weight)
    obj.data.update()


def _flatten_group(surface, objects):
    """Remove the residual slope of a tabletop or seat from its whole assembly."""
    surface.data.update()
    top = max(surface.data.polygons, key=lambda face: face.area if face.normal.z > .5 else -1)
    normal = top.normal.copy()
    if normal.z < .5:
        raise ValueError(f"No upward supporting surface on {surface.name}")
    center = top.center.copy()
    for obj in objects:
        for vertex in obj.data.vertices:
            vertex.co.z += (normal.x * (vertex.co.x - center.x)
                            + normal.y * (vertex.co.y - center.y)) / normal.z
        obj.data.update()
    # Authored quads have a small residual twist. Their physical supporting
    # faces use exact horizontal planes after the assembly's shear is removed.
    for direction in (1, -1):
        face = max(surface.data.polygons,
                   key=lambda polygon: polygon.area if polygon.normal.z * direction > .5 else -1)
        height = sum(surface.data.vertices[index].co.z for index in face.vertices) / len(face.vertices)
        for index in face.vertices:
            surface.data.vertices[index].co.z = height
    surface.data.update()


def _leg_to_floor(obj, floor):
    low, high = _limits([obj])
    top_points = [vertex.co for vertex in obj.data.vertices if vertex.co.z > high.z - 3]
    bottom_points = [vertex.co for vertex in obj.data.vertices if vertex.co.z < low.z + 3]
    top_center = sum(top_points, Vector()) / len(top_points)
    bottom_center = sum(bottom_points, Vector()) / len(bottom_points)
    shift = Vector((top_center.x - bottom_center.x, top_center.y - bottom_center.y, floor - .15 - low.z))
    height = high.z - low.z
    if high.z < floor + 4:
        raise ValueError(f"Support top is below its floor: {obj.name}")
    for vertex in obj.data.vertices:
        weight = min(1, max(0, (high.z - 4 - vertex.co.z) / max(1, height - 7)))
        vertex.co += shift * weight
    obj.data.update()


def _world_shape(obj):
    points = [vertex.co.copy() for vertex in obj.data.vertices]
    return points, BVHTree.FromPolygons(points, [list(face.vertices) for face in obj.data.polygons])


def _mount(api, name, first, second, radius=2):
    """Add a short solid fitting only if two intended mounting surfaces separate."""
    a_points, a = _world_shape(first)
    b_points, b = _world_shape(second)
    if a.overlap(b):
        return
    candidates = [(b.find_nearest(point)[3], point, b.find_nearest(point)[0]) for point in a_points]
    candidates += [(a.find_nearest(point)[3], a.find_nearest(point)[0], point) for point in b_points]
    distance, start, end = min(candidates, key=lambda item: item[0])
    if distance < .25:
        return
    direction = (end - start).normalized()
    start -= direction * radius
    end += direction * radius
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=radius, depth=(end - start).length,
                                      end_fill_type="NGON", location=(start + end) / 2)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    fill = first.get("sourceFill", "blue")
    obj.data.materials.append(api.material(fill))
    obj["sourceFill"] = fill
    obj["coordinateSpace"] = "world"
    obj["connectsFirst"] = first.name
    obj["connectsSecond"] = second.name


def _chair(api, room_name, objects, room):
    prefix = f"Interior_{room_name}_"
    chair = [obj for name, obj in objects.items() if "Chair" in name or "Lumbar" in name]
    seat = objects[prefix + "ChairSeat"]
    _flatten_group(seat, chair)
    _, seat_high = _limits([seat])
    _move(chair, Vector((0, 0, room["floorZ"] + 44 - seat_high.z)))
    hub = objects[prefix + "Chair_Hub"]
    old_hub = _center(hub)
    hub_shift = Vector((0, 0, room["floorZ"] + 11 - old_hub.z))
    _move([hub], hub_shift)
    lift = objects[prefix + "Chair_GasLift"]
    top = max((vertex.co for vertex in lift.data.vertices), key=lambda point: point.z).copy()
    _bend(lift, top, old_hub, Vector(), hub_shift)
    for index in range(5):
        caster = objects[prefix + f"Chair_Caster_{index}"]
        old_caster = _center(caster)
        low, _ = _limits([caster])
        shift = Vector((0, 0, room["floorZ"] - .1 - low.z))
        _move([caster], shift)
        spoke = objects[prefix + f"Chair_Spoke_{index}"]
        _bend(spoke, old_hub, old_caster, hub_shift, shift)
        caster["floorSupport"] = "WorldArchitecture_BuildingShell"
        _mount(api, caster.name + "_WorldAxle", caster, spoke, 1.8)
        _mount(api, spoke.name + "_WorldHubMount", spoke, hub, 2)
    _mount(api, lift.name + "_WorldSeatMount", lift, seat, 3)


def _wall_fixtures(objects, room):
    for poster in ("LeftPoster", "RightPoster"):
        name = f"Interior_Gaming_{poster}_Frame"
        if name in objects:
            frame = objects[name]
            print_obj = objects[name.replace("_Frame", "_Print")]
            _, high = _limits([frame])
            group = [frame, print_obj]
            _move(group, Vector((0, room["y"][1] + .1 - high.y, 0)))
            low, high = _limits(group)
            # The reference camera looks down into a deep room. Rear-wall art
            # must fit below the ceiling's projected sightline, not just below
            # the ceiling in world coordinates. Preserve the print's aspect.
            visible_top = (room["ceilingZ"] - 10
                           + AWAY.z / AWAY.y * (high.y - room["frontY"]))
            visible_bottom = room["floorZ"] + 9
            scale = min(1, (visible_top - visible_bottom) / (high.z - low.z))
            center = (low + high) / 2
            for obj in group:
                for vertex in obj.data.vertices:
                    vertex.co.x = center.x + (vertex.co.x - center.x) * scale
                    vertex.co.z = center.z + (vertex.co.z - center.z) * scale
                obj.data.update()
            low, high = _limits(group)
            z_shift = min(0, visible_top - high.z)
            z_shift = max(z_shift, visible_bottom - low.z)
            front = [vertex.co - AWAY * ((vertex.co.y - room["frontY"]) / AWAY.y)
                     for obj in group for vertex in obj.data.vertices]
            left = room["openingX"][0] + 10
            right = room["openingX"][1] - 10
            x_shift = max(0, left - min(point.x for point in front))
            x_shift = min(x_shift, right - max(point.x for point in front))
            _move(group, Vector((x_shift, 0, z_shift)))
            frame["mountedTo"] = "WorldArchitecture_BuildingShell"
    controls = objects.get("Interior_Kitchen_WallControls")
    if controls:
        group = [obj for name, obj in objects.items() if "WallControls" in name or "ControlLamp" in name]
        center = _center(controls)
        rotation = Matrix.Rotation(-math.pi / 2, 3, "Z")
        for obj in group:
            for vertex in obj.data.vertices:
                vertex.co = center + rotation @ (vertex.co - center)
            obj.data.update()
        _, high = _limits([controls])
        _move(group, Vector((room["x"][1] + .1 - high.x,
                             room["y"][1] - 60 - _center(controls).y, 0)))
        controls["mountedTo"] = "WorldArchitecture_BuildingShell"


def _recording_supports(api, objects, room):
    for base_name, stem_name in (("MicrophoneBase", "MicrophoneStand"), ("RearMicBase", "RearMicPole")):
        base = objects["Interior_Recording_" + base_name]
        stem = objects["Interior_Recording_" + stem_name]
        old_base = _center(base)
        low, _ = _limits([base])
        offset = Vector((0, 0, room["floorZ"] - .1 - low.z))
        _move([base], offset)
        top = max((vertex.co for vertex in stem.data.vertices), key=lambda point: point.z).copy()
        _bend(stem, top, old_base, Vector(), offset)
        _mount(api, base.name + "_WorldStemMount", base, stem, 2)
        base["floorSupport"] = "WorldArchitecture_BuildingShell"
    stem = objects["Interior_Recording_LampStem"]
    low, high = _limits([stem])
    shift = room["ceilingZ"] + .1 - high.z
    for vertex in stem.data.vertices:
        weight = max(0, min(1, (vertex.co.z - low.z - 2) / max(1, high.z - low.z - 4)))
        vertex.co.z += shift * weight
    stem.data.update()
    stem["mountedTo"] = "WorldArchitecture_BuildingShell"


def _cabinet_supports(objects):
    body = objects["Interior_Kitchen_CabinetBody"]
    _, body_tree = _world_shape(body)
    for name, foot in objects.items():
        if "CabinetFoot_" not in name:
            continue
        _, foot_tree = _world_shape(foot)
        if body_tree.overlap(foot_tree):
            continue
        low, high = _limits([foot])
        top = (low + high) / 2
        top.z = high.z + .001
        contact, _, _, distance = body_tree.ray_cast(top, Vector((0, 0, 1)))
        if contact is None:
            raise ValueError(f"Cabinet body is not above its supporting foot: {name}")
        # Preserve the planted bottom while extending the upper foot into the
        # sloped underside of the authored cabinet body.
        for vertex in foot.data.vertices:
            weight = max(0, min(1, (vertex.co.z - low.z - 3) / (high.z - low.z - 3)))
            vertex.co.z += weight * (distance + 1.25)
        foot.data.update()


def _recording_composition():
    groups = ((65, ("Microphone", "RearMic")), (60, ("Chair", "Lumbar")), (50, ("Lamp",)))
    for offset, names in groups:
        objects = [obj for obj in bpy.context.scene.objects
                   if obj.type == "MESH" and obj.name.startswith("Interior_Recording_")
                   and any(name in obj.name for name in names)]
        _move(objects, Vector((offset, 0, 0)))


def adapt_interiors_to_world(api, rooms):
    """De-shear existing Interior_* solids and constrain them to the canonical rooms."""
    for room_name, axes in ROOM_AXES.items():
        prefix = f"Interior_{room_name}_"
        objects = {obj.name: obj for obj in sorted(bpy.context.scene.objects, key=lambda obj: obj.name)
                   if obj.type == "MESH" and obj.name.startswith(prefix)}
        if not objects:
            raise ValueError(f"Missing authored furniture for {room_name}")
        room = rooms[room_name]
        for obj in objects.values():
            if obj.data.attributes.get("SourcePosition") is None:
                raise ValueError(f"Missing source-art positions on {obj.name}")
            obj.data.transform(obj.matrix_world)
            obj.matrix_world = Matrix.Identity(4)
            for vertex in obj.data.vertices:
                x = vertex.co.x + axes["shear"] * vertex.co.y
                vertex.co = (x, vertex.co.y, vertex.co.z - axes["slope"] * x - axes["rise"] * vertex.co.y)
            obj.data.update()

        low, high = _limits(objects.values())
        sx, sy, sz = axes["scale"]
        usable_left = room.get("usableX", room["x"])[0]
        left_margin = 75 if room_name == "Recording" else 10
        sx = min(sx, (room["x"][1] - usable_left - left_margin - 10) / (high.x - low.x))
        sy = min(sy, (room["y"][1] - room["frontY"] - 35) / (high.y - low.y))
        bases = [obj for name, obj in objects.items() if "Caster_" in name or "CabinetFoot_" in name]
        floor_anchor = _limits(bases)[0].z
        offset = Vector((usable_left + left_margin - low.x * sx,
                         room["frontY"] + 20 - low.y * sy,
                         room["floorZ"] - floor_anchor * sz))
        for obj in objects.values():
            for vertex in obj.data.vertices:
                point = vertex.co
                vertex.co = Vector((point.x * sx, point.y * sy, point.z * sz)) + offset
            obj.data.update()
            obj["coordinateSpace"] = "world"
            obj["room"] = room_name
            obj["artworkCoordinates"] = "Preserved SourcePosition attribute from authored furniture."

        if room_name == "Gaming":
            desk_group = [obj for name, obj in objects.items()
                          if "Chair" not in name and "Poster" not in name and "Subwoofer" not in name]
            _flatten_group(objects[prefix + "DeskTop"], desk_group)
        elif room_name == "Workspace":
            desk_group = [obj for name, obj in objects.items() if "Chair" not in name and "Lumbar" not in name]
            _flatten_group(objects[prefix + "DeskTop"], desk_group)
            monitors = [obj for name, obj in objects.items() if "LeftMonitor" in name or "RightMonitor" in name]
            _move(monitors, Vector((14, 0, 0)))
        elif room_name == "Recording":
            desk_group = [obj for name, obj in objects.items()
                          if any(part in name for part in ("Console", "Mixing", "Speaker", "Fader"))]
            _flatten_group(objects[prefix + "ConsoleDesk"], desk_group)
            top_height = max(vertex.co.z for vertex in objects[prefix + "ConsoleDesk"].data.vertices)
            _move(desk_group, Vector((0, 0, room["floorZ"] + 58 - top_height)))
        else:
            desk_group = [obj for name, obj in objects.items() if "Control" not in name]
            _flatten_group(objects[prefix + "CounterTop"], desk_group)

        for name, obj in objects.items():
            if any(part in name for part in ("DeskLeg_", "ConsoleLeg_", "CabinetFoot_")):
                _leg_to_floor(obj, room["floorZ"])
                obj["floorSupport"] = "WorldArchitecture_BuildingShell"
        if room_name != "Kitchen":
            _chair(api, room_name, objects, room)
        if room_name == "Recording":
            _recording_supports(api, objects, room)
            _recording_composition()
        if room_name == "Kitchen":
            _cabinet_supports(objects)
        if room_name == "Gaming":
            cabinet = objects[prefix + "Subwoofer"]
            low, _ = _limits([cabinet])
            _move([cabinet, objects[prefix + "SubwooferCone"]], Vector((0, 0, room["floorZ"] - .1 - low.z)))
            cabinet["floorSupport"] = "WorldArchitecture_BuildingShell"
        _wall_fixtures(objects, room)
        if room_name == "Workspace":
            group = [obj for obj in bpy.context.scene.objects
                     if obj.type == "MESH" and obj.name.startswith(prefix)]
            _, high = _limits(group)
            shift = min(36, max(0, room["x"][1] - 10 - high.x))
            if shift < .001:
                shift = 0
            _move(group, Vector((shift, 0, 0)))
            print(f"WORLD WORKSPACE X SHIFT {shift:.3f}", flush=True)

        for obj in objects.values():
            obj.data.update()
            if "surfaceGroups" in obj:
                del obj["surfaceGroups"]
