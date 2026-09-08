"""Adapt editable furniture to orthogonal world rooms without changing artwork coordinates."""

import math

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from world import AWAY, SCALE, unproject


ROOMS = ("Gaming", "Workspace", "Kitchen", "Recording")


def _along_view(objects, distance):
    """Move an assembly along the reference camera's line of sight.

    Its painted position is unchanged: only its depth in the world moves.
    """
    _move(objects, AWAY * (distance / SCALE))


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
            group = [frame, print_obj]
            _, high = _limits([frame])
            # Slide the poster back along the sightline until it hangs on the rear wall.
            _along_view(group, (room["y"][1] - .1 - high.y) * SCALE / AWAY.y)
            low, high = _limits(group)
            z_shift = min(0, room["ceilingZ"] - 4 - high.z)
            z_shift = max(z_shift, room["floorZ"] + 4 - low.z)
            x_shift = max(0, room["x"][0] + 4 - low.x)
            x_shift = min(x_shift, room["x"][1] - 4 - high.x)
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
        _along_view(group, (room["x"][1] + .1 - high.x) * SCALE / AWAY.x)
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


def adapt_interiors_to_world(api, rooms):
    """Unproject authored furniture through the fitted camera into the canonical rooms.

    Every vertex keeps its painted position; only its depth along the line
    of sight is chosen, so each room's floor-standing pieces meet the floor.
    """
    for room_name in ROOMS:
        prefix = f"Interior_{room_name}_"
        objects = {obj.name: obj for obj in sorted(bpy.context.scene.objects, key=lambda obj: obj.name)
                   if obj.type == "MESH" and obj.name.startswith(prefix)}
        if not objects:
            raise ValueError(f"Missing authored furniture for {room_name}")
        room = rooms[room_name]
        for obj in objects.values():
            if obj.data.attributes.get("SourcePosition") is None:
                raise ValueError(f"Missing source-art positions on {obj.name}")
            matrix = obj.matrix_world.copy()
            for vertex in obj.data.vertices:
                p = matrix @ vertex.co
                # Authored space is (u, depth, 1024 - v) in painting pixels.
                vertex.co = unproject((p.x, 1024 - p.z, p.y))
            obj.matrix_world = Matrix.Identity(4)
            obj.data.update()

        bases = [obj for name, obj in objects.items()
                 if any(part in name for part in ("Caster_", "CabinetFoot_", "DeskLeg_", "ConsoleLeg_", "MicrophoneBase", "RearMicBase"))]
        if not bases:
            raise ValueError(f"No floor-standing pieces in {room_name}")
        lowest = _limits(bases)[0].z
        _along_view(objects.values(), (room["floorZ"] + .1 - lowest) * SCALE / AWAY.z)
        low, high = _limits(objects.values())
        overshoot = high.y - (room["y"][1] - 2)
        if overshoot > 0:
            # The painting places this room deeper than its cavity; pull it forward.
            _along_view(objects.values(), -overshoot * SCALE / AWAY.y)
            print(f"WORLD {room_name.upper()} PULLED FORWARD {overshoot:.1f}", flush=True)
        for obj in objects.values():
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
        if room_name == "Kitchen":
            _cabinet_supports(objects)
        if room_name == "Gaming":
            cabinet = objects[prefix + "Subwoofer"]
            low, _ = _limits([cabinet])
            _move([cabinet, objects[prefix + "SubwooferCone"]], Vector((0, 0, room["floorZ"] - .1 - low.z)))
            cabinet["floorSupport"] = "WorldArchitecture_BuildingShell"
        _wall_fixtures(objects, room)

        for obj in objects.values():
            obj.data.update()
            if "surfaceGroups" in obj:
                del obj["surfaceGroups"]
