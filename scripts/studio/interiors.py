"""Individually modeled furniture and equipment in the four illustrated rooms."""

import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from common import rounded_quad


def _mesh(api, name, vertices, faces, fill="blue"):
    obj = api.mesh(name, vertices, faces)
    obj["sourceFill"] = fill
    return obj


def _slab(api, name, top, thickness=7, fill="gold"):
    """A horizontal or sloped slab, with depth specified at every corner."""
    count = len(top)
    vertices = top + [(u, v + thickness, d) for u, v, d in top]
    faces = [tuple(range(count)), tuple(reversed(range(count, count * 2)))]
    faces += [(i, (i + 1) % count, (i + 1) % count + count, i + count)
              for i in range(count)]
    return _mesh(api, name, vertices, faces, fill)


def _curved_panel(api, name, outline, front, thickness=9, bulge=3, fill="blue"):
    """A padded solid with a bowed face and a separately closed rear shell."""
    count = len(outline)
    depths = [front(u, v) if callable(front) else front for u, v in outline]
    center = (sum(p[0] for p in outline) / count,
              sum(p[1] for p in outline) / count,
              sum(depths) / count - bulge)
    vertices = [(u, v, d) for (u, v), d in zip(outline, depths)]
    vertices += [(u - thickness * .12, v - thickness * .1, d + thickness)
                 for (u, v), d in zip(outline, depths)]
    vertices += [center, (center[0], center[1], center[2] + thickness + bulge)]
    faces = [(2 * count, i, (i + 1) % count) for i in range(count)]
    faces += [(2 * count + 1, (i + 1) % count + count, i + count)
              for i in range(count)]
    faces += [(i, i + count, (i + 1) % count + count, (i + 1) % count)
              for i in range(count)]
    return _mesh(api, name, vertices, faces, fill)


def _tube(api, name, points, radius, fill="blue"):
    return api.tube(name, points, radius, material=fill, project=True)


def _rounded(api, name, corners, front, thickness, radius=3, fill="blue"):
    obj = api.solid(name, rounded_quad(corners, radius, 5), front,
                    thickness, (-.18, -.13), side_material=fill)
    obj["sourceFill"] = fill
    obj["supportTopEdge"] = [*corners[0], *corners[1]]
    return obj


def _ellipsoid(api, name, center, radii, fill="blue"):
    obj = api.ellipsoid(name, center, radii)
    obj["sourceFill"] = fill
    return obj


def _quad_point(quad, u, v):
    return tuple((1 - v) * ((1 - u) * quad[0][axis] + u * quad[1][axis])
                 + v * ((1 - u) * quad[3][axis] + u * quad[2][axis])
                 for axis in range(3))


def _keycaps(api, name, quad, rows, columns):
    for row in range(rows):
        for col in range(columns):
            left, right = (col + .12) / columns, (col + .86) / columns
            top, bottom = (row + .16) / rows, (row + .81) / rows
            points = [_quad_point(quad, x, y)
                      for x, y in [(left, top), (right, top),
                                   (right, bottom), (left, bottom)]]
            points = [(u, v - .55, d) for u, v, d in points]
            _slab(api, f"{name}_Key_{row:02}_{col:02}", points, .75, "blue")


def _monitor(api, name, frame, depth, screen, stand, foot):
    _rounded(api, f"{name}_Housing", frame, depth, 10, 2.5)
    api.solid(f"{name}_Screen", screen, depth - .6, 1,
              (0, 0), side_material="pink")
    _tube(api, f"{name}_Stand", stand, 3.1)
    _slab(api, f"{name}_Foot", foot, 2.5, "blue")


def _wheelbase(api, name, center, endpoints, depth):
    x, y = center
    _tube(api, f"{name}_GasLift", [(x, y - 17, depth + 8), (x, y, depth)], 3)
    _ellipsoid(api, f"{name}_Hub", (x, y, depth), (5, 3, 5))
    for index, (u, v, offset) in enumerate(endpoints):
        _tube(api, f"{name}_Spoke_{index}",
              [(x, y, depth), ((x + u) / 2, (y + v) / 2 - 1, depth + offset / 2),
               (u, v, depth + offset)], [3.2, 2.6, 2.1])
        _ellipsoid(api, f"{name}_Caster_{index}",
                   (u, v + 2, depth + offset), (5.2, 3.2, 4.3))


def _revolved(api, name, center, profile, depth, ellipse=.25, fill="blue", segments=48):
    """Revolve a vessel profile, preserving a genuine open cavity at its lip."""
    cx, cy = center
    vertices, faces = [], []
    for radius, height in profile:
        for step in range(segments):
            angle = step * math.tau / segments
            vertices.append((cx + radius * math.cos(angle),
                             cy + height + radius * ellipse * math.sin(angle),
                             depth - radius * .8 * math.sin(angle)))
    for ring in range(len(profile) - 1):
        for step in range(segments):
            a = ring * segments + step
            b = ring * segments + (step + 1) % segments
            faces.append((a, b, b + segments, a + segments))
    if profile[0][0] > 0 and profile[-1][0] > 0 and profile[0] != profile[-1]:
        last = (len(profile) - 1) * segments
        faces += [(step, last + step, last + (step + 1) % segments,
                   (step + 1) % segments) for step in range(segments)]
    return _mesh(api, name, vertices, faces, fill)


def _repair_volume(obj):
    """Weld coincident poles/seams and orient the complete solid consistently."""
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    bmesh.ops.remove_doubles(mesh, verts=list(mesh.verts), dist=.0001)
    bmesh.ops.dissolve_degenerate(mesh, edges=list(mesh.edges), dist=.000001)
    bmesh.ops.recalc_face_normals(mesh, faces=list(mesh.faces))
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()


def _world_shape(obj):
    vertices = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return vertices, BVHTree.FromPolygons(vertices, [list(face.vertices) for face in obj.data.polygons])


def _extend_support_to_top(support, top):
    """Extend a leg or carcass vertically until its upper end enters its top."""
    _, surface = _world_shape(top)
    x0, v0, x1, v1 = support["supportTopEdge"]
    selected = []
    shifts = []
    for vertex in support.data.vertices:
        edge_v = v0 + (v1 - v0) * (vertex.co.x - x0) / (x1 - x0)
        if 1024 - vertex.co.z > edge_v + 12:
            continue
        selected.append(vertex)
        position = support.matrix_world @ vertex.co
        hit, _, _, _ = surface.ray_cast(position - Vector((0, 0, 300)), Vector((0, 0, 1)), 600)
        if hit is not None:
            shifts.append(hit.z + 1.5 - position.z)
    if shifts:
        extension = max(0, max(shifts))
        for vertex in selected:
            vertex.co.z += extension
    support.data.update()


def _connect_parts(api, name, first, second, radius, fill="blue"):
    """Add a short physical mounting stem between separated assembled parts."""
    first_vertices, first_surface = _world_shape(first)
    second_vertices, second_surface = _world_shape(second)
    if first_surface.overlap(second_surface):
        return
    candidates = []
    for position in first_vertices:
        nearest, _, _, distance = second_surface.find_nearest(position)
        candidates.append((distance, position, nearest))
    for position in second_vertices:
        nearest, _, _, distance = first_surface.find_nearest(position)
        candidates.append((distance, nearest, position))
    distance, start, end = min(candidates, key=lambda candidate: candidate[0])
    if distance < .05:
        return
    direction = (end - start).normalized()
    start -= direction * radius
    end += direction * radius
    points = [(position.x, 1024 - position.z, position.y) for position in (start, end)]
    mount = _tube(api, name, points, radius, fill)
    mount["connectsFirst"] = first.name
    mount["connectsSecond"] = second.name


def _seat_detail(detail, support):
    """Seat a small control into its supporting face without shifting its image position."""
    _, surface = _world_shape(support)
    overlaps = []
    for vertex in detail.data.vertices:
        position = detail.matrix_world @ vertex.co
        origin = Vector((position.x, -1000, position.z))
        hit, _, _, _ = surface.ray_cast(origin, Vector((0, 1, 0)), 5000)
        if hit is not None:
            overlaps.append(position.y - hit.y)
    if overlaps:
        shift = .35 - max(overlaps)
        for vertex in detail.data.vertices:
            vertex.co.y += shift
        detail.data.update()


def _mount_wall_fixtures(api, objects):
    """Attach wall fixtures to the current shell without changing image coordinates."""
    upper = bpy.data.objects.get("Architecture • continuous upper storey")
    lower = bpy.data.objects.get("Architecture • continuous ground storey")
    middle = bpy.data.objects.get("Architecture • continuous middle storey")
    if upper:
        for poster in ("LeftPoster", "RightPoster"):
            for part in ("Frame", "Print"):
                obj = objects[f"Interior_Gaming_{poster}_{part}"]
                for vertex in obj.data.vertices:
                    vertex.co.y += 11.35
                obj.data.update()
            objects[f"Interior_Gaming_{poster}_Frame"]["mountedTo"] = upper.name
    if lower:
        _, surface = _world_shape(lower)
        for name, obj in objects.items():
            if name == "Interior_Kitchen_WallControls" or name.startswith("Interior_Kitchen_ControlLamp"):
                for vertex in obj.data.vertices:
                    position = obj.matrix_world @ vertex.co
                    hit, _, _, _ = surface.ray_cast(
                        Vector((position.x, -1000, position.z)), Vector((0, 1, 0)), 5000)
                    if hit is not None:
                        vertex.co.y += hit.y + .35 - 156
                obj.data.update()
        objects["Interior_Kitchen_WallControls"]["mountedTo"] = lower.name
    if middle:
        stem = objects["Interior_Recording_LampStem"]
        _connect_parts(api, "Interior_Recording_LampCeilingMount", stem, middle, 3, "gold")


def _room_floor(shell, room):
    """Select the upward cavity floor faces, then measure their actual triangles."""
    vertices = [shell.matrix_world @ vertex.co for vertex in shell.data.vertices]
    faces = []
    lower_aperture = {"Gaming": 440, "Recording": 615, "Workspace": 850, "Kitchen": 840}[room]
    for polygon in shell.data.polygons:
        points = [vertices[index] for index in polygon.vertices]
        center = sum(points, Vector()) / len(points)
        depths = [point.y for point in points]
        if (polygon.normal.z <= .5 or min(depths) >= 0 or max(depths) <= 100
                or 1024 - center.z <= lower_aperture):
            continue
        if room == "Workspace" and center.x > 770:
            continue
        if room == "Kitchen" and center.x < 770:
            continue
        faces.append(list(polygon.vertices))
    if not faces:
        raise ValueError(f"No upward cavity floor found for {room}")
    return BVHTree.FromPolygons(vertices, faces)


def _floor_adjustment(obj, floor):
    """Prefer a depth shift; use height only where the bounded floor requires it."""
    vertices = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    bottom = min(point.z for point in vertices)
    samples = [point for point in vertices if point.z < bottom + 1.5]
    candidates = []
    for depth_shift in range(-100, 101, 2):
        gaps = []
        for point in samples:
            origin = point + Vector((0, depth_shift, 500))
            hit, _, _, _ = floor.ray_cast(origin, Vector((0, 0, -1)), 1000)
            if hit is not None:
                gaps.append(point.z - hit.z)
        if len(gaps) < len(samples) * .95:
            continue
        height_shift = -min(gaps) - .12
        score = abs(height_shift) + abs(depth_shift) * .12
        candidates.append((score, abs(depth_shift), depth_shift, height_shift))
    if not candidates:
        raise ValueError(f"No cavity floor can support {obj.name}")
    _, _, depth_shift, height_shift = min(candidates)
    return Vector((0, depth_shift, height_shift))


def _center(obj):
    points = [vertex.co for vertex in obj.data.vertices]
    return Vector(tuple((min(point[axis] for point in points) + max(point[axis] for point in points)) / 2
                        for axis in range(3)))


def _translate(obj, offset):
    for vertex in obj.data.vertices:
        vertex.co += offset
    obj.data.update()


def _bend_support(obj, first, second, first_shift, second_shift):
    """Move a support's endpoints while retaining its thickness and shared contact."""
    axis = second - first
    length_squared = axis.length_squared
    for vertex in obj.data.vertices:
        weight = max(0, min(1, (vertex.co - first).dot(axis) / length_squared))
        vertex.co += first_shift.lerp(second_shift, weight)
    obj.data.update()


def _seat_floor_supports(api, objects):
    for room, storey in (("Gaming", "upper"), ("Recording", "middle"),
                         ("Workspace", "ground"), ("Kitchen", "ground")):
        shell = bpy.data.objects.get(f"Architecture • continuous {storey} storey")
        if shell is None:
            continue
        floor = _room_floor(shell, room)
        prefix = f"Interior_{room}_"
        if room != "Kitchen":
            hub = objects[prefix + "Chair_Hub"]
            old_hub = _center(hub)
            hit, _, _, _ = floor.ray_cast(old_hub + Vector((0, 0, 500)), Vector((0, 0, -1)), 1000)
            if hit is None:
                raise ValueError(f"Chair hub lies outside the {room} floor")
            hub_shift = Vector((0, 0, max(0, hit.z + 7 - old_hub.z)))
            _translate(hub, hub_shift)
            lift = objects[prefix + "Chair_GasLift"]
            _bend_support(lift, old_hub + Vector((0, 8, 17)), old_hub, Vector(), hub_shift)
            for index in range(5):
                caster = objects[prefix + f"Chair_Caster_{index}"]
                old_caster = _center(caster)
                offset = _floor_adjustment(caster, floor)
                _translate(caster, offset)
                spoke = objects[prefix + f"Chair_Spoke_{index}"]
                _bend_support(spoke, old_hub, old_caster, hub_shift, offset)
                caster["floorSupport"] = shell.name
                caster["floorAdjustment"] = list(offset)
        support_names = [name for name in objects if name.startswith(prefix)
                         and any(part in name for part in ("DeskLeg_", "ConsoleLeg_", "CabinetFoot_"))]
        for name in support_names:
            obj = objects[name]
            offset = _floor_adjustment(obj, floor)
            if "CabinetFoot" in name:
                depths = [vertex.co.y for vertex in obj.data.vertices]
                front, rear = min(depths), max(depths)
                for vertex in obj.data.vertices:
                    weight = (rear - vertex.co.y) / (rear - front)
                    vertex.co += offset * weight
                obj.data.update()
            else:
                points = [vertex.co for vertex in obj.data.vertices]
                top = max(point.z for point in points)
                bottom = min(point.z for point in points)
                for vertex in obj.data.vertices:
                    weight = min(1, (top - vertex.co.z) / max(1, top - bottom - 4))
                    vertex.co += offset * weight
                obj.data.update()
            obj["floorSupport"] = shell.name
            obj["floorAdjustment"] = list(offset)
        if room == "Recording":
            for base_name, stem_name in (("MicrophoneBase", "MicrophoneStand"), ("RearMicBase", "RearMicPole")):
                base = objects[prefix + base_name]
                stem = objects[prefix + stem_name]
                old_base = _center(base)
                offset = _floor_adjustment(base, floor)
                _translate(base, offset)
                top = max((vertex.co for vertex in stem.data.vertices), key=lambda point: point.z).copy()
                _bend_support(stem, top, old_base, Vector(), offset)
                _connect_parts(api, prefix + base_name + "_StemMount", base, stem, 2.5)
                base["floorSupport"] = shell.name
                base["floorAdjustment"] = list(offset)
        if room == "Gaming":
            cabinet = objects[prefix + "Subwoofer"]
            offset = _floor_adjustment(cabinet, floor)
            _translate(cabinet, offset)
            _translate(objects[prefix + "SubwooferCone"], offset)
            cabinet["floorSupport"] = shell.name
            cabinet["floorAdjustment"] = list(offset)


def _desktop_room(api):
    prefix = "Interior_Gaming"
    _slab(api, f"{prefix}_DeskTop",
          [(594, 438, 133), (828, 414, 133), (864, 429, 62), (596, 454, 62)], 7)
    for index, corners in enumerate([
        [(597, 458), (604, 457), (604, 490), (598, 491)],
        [(826, 439), (834, 438), (834, 475), (827, 476)],
    ]):
        _rounded(api, f"{prefix}_DeskLeg_{index}", corners, 95, 9, 1.3)

    _monitor(api, f"{prefix}_MainMonitor",
             [(670, 327), (782, 318), (785, 408), (672, 419)], 105,
             [(680, 336), (773, 328), (775, 399), (681, 409)],
             [(729, 411, 113), (729, 424, 109)],
             [(714, 423, 107), (736, 421, 113), (748, 425, 94), (726, 428, 91)])

    for name, outer, inner in [
        ("LeftPoster", [(594, 330), (657, 325), (658, 433), (595, 440)],
         [(600, 336), (651, 331), (652, 428), (600, 433)]),
        ("RightPoster", [(834, 310), (879, 322), (880, 424), (834, 412)],
         [(839, 317), (875, 326), (875, 417), (839, 409)]),
    ]:
        api.solid(f"{prefix}_{name}_Frame", outer, 151, 3,
                  (0, 0), side_material="gold")
        api.solid(f"{prefix}_{name}_Print", inner, 150.5, .6,
                  (0, 0), side_material="pink")

    tower_vertices = [
        (812, 359, 85), (845, 354, 85), (846, 421, 85), (813, 427, 85),
        (785, 349, 124), (817, 344, 124), (818, 410, 124), (786, 416, 124),
    ]
    _mesh(api, f"{prefix}_ComputerCase", tower_vertices,
          [(0, 1, 2, 3), (0, 4, 5, 1), (0, 3, 7, 4),
           (1, 5, 6, 2), (3, 2, 6, 7), (4, 7, 6, 5)])
    for index, center in enumerate([(800, 375), (800, 400)]):
        _ellipsoid(api, f"{prefix}_CaseFan_{index}", (*center, 98), (8.2, 11, 10), "pink")
    for index, (x, y, radius) in enumerate([(833, 386, 5), (833, 407, 5.5)]):
        _ellipsoid(api, f"{prefix}_FrontFan_{index}", (x, y, 81), (radius, radius + 2, 5))
    for index, y in enumerate([369, 374]):
        _rounded(api, f"{prefix}_DriveSlot_{index}",
                 [(820, y), (839, y - 1), (839, y + 2), (820, y + 3)], 81, 2, .5)

    keyboard = [(709, 424, 112), (763, 420, 112), (777, 434, 85), (717, 439, 85)]
    _slab(api, f"{prefix}_Keyboard", keyboard, 2.5)
    _keycaps(api, f"{prefix}_Keyboard", keyboard, 4, 13)
    _slab(api, f"{prefix}_MouseMat",
          [(774, 420, 112), (789, 419, 113), (805, 433, 87), (786, 436, 85)], .8, "blue")
    _ellipsoid(api, f"{prefix}_Mouse", (789, 426, 97), (7, 4.5, 5), "cream")

    _rounded(api, f"{prefix}_Subwoofer",
             [(826, 447), (860, 443), (862, 480), (828, 484)], 96, 25, 2)
    _ellipsoid(api, f"{prefix}_SubwooferCone", (846, 463, 91), (11.5, 13.5, 7), "pink")

    for index, x in enumerate([612, 636]):
        _ellipsoid(api, f"{prefix}_Figurine_{index}_Plinth", (x, 442, 88), (8, 2.6, 6))
        _tube(api, f"{prefix}_Figurine_{index}_LeftLeg",
              [(x - 2, 438, 91), (x - 2, 430, 95)], 1.5, "gold")
        _tube(api, f"{prefix}_Figurine_{index}_RightLeg",
              [(x + 2, 438, 91), (x + 1, 430, 95)], 1.5, "gold")
        _ellipsoid(api, f"{prefix}_Figurine_{index}_Body", (x, 426, 96), (4, 7, 3.5))
        _ellipsoid(api, f"{prefix}_Figurine_{index}_Head", (x, 416, 97), (3.4, 3.9, 3))

    gaming_outline = [
        (669, 390), (680, 389), (689, 395), (695, 410), (704, 419),
        (708, 453), (703, 469), (693, 478), (673, 475), (662, 465),
        (656, 447), (652, 425), (656, 415), (661, 409), (662, 398),
    ]
    _curved_panel(api, f"{prefix}_ChairBack", gaming_outline,
                  lambda u, v: 31 + (477 - v) * .42, 12, 4)
    _slab(api, f"{prefix}_ChairSeat",
          [(678, 471, 59), (703, 467, 62), (717, 477, 25), (692, 485, 24)], 5, "pink")
    _tube(api, f"{prefix}_ChairRightArmUpright",
          [(713, 481, 39), (716, 464, 34)], 2.4)
    _curved_panel(api, f"{prefix}_ChairRightArmPad",
                  [(709, 459), (731, 455), (736, 459), (731, 464), (711, 468)], 29, 5, 1)
    _tube(api, f"{prefix}_ChairLeftArm",
          [(665, 467, 49), (662, 456, 43), (656, 455, 40)], 2)
    _wheelbase(api, f"{prefix}_Chair", (689, 494),
               [(662, 497, 1), (677, 505, -8), (715, 503, -4),
                (709, 486, 21), (675, 486, 23)], 35)


def _recording_room(api):
    prefix = "Interior_Recording"
    _tube(api, f"{prefix}_LampStem", [(677, 522, 108), (680, 536, 100)], [3, 4], "gold")
    _revolved(api, f"{prefix}_LampShade", (683, 549),
              [(3, -19), (13, -14), (23, -4), (28, 7), (24, 9), (3, -13)], 93, .23, "pink")
    _ellipsoid(api, f"{prefix}_LampBulb", (682, 557, 88), (14, 3.4, 7), "cream")

    _tube(api, f"{prefix}_RearMicPole", [(608, 636, 116), (609, 579, 119)], 1.8)
    _ellipsoid(api, f"{prefix}_RearMicBase", (607, 635, 112), (12, 3.6, 10))
    _tube(api, f"{prefix}_MicrophoneStand", [(635, 649, 57), (635, 599, 70)], 2.7)
    _ellipsoid(api, f"{prefix}_MicrophoneBase", (635, 653, 49), (22, 5.9, 14))
    _ellipsoid(api, f"{prefix}_MicrophoneBody", (635, 584, 72), (7.3, 20.2, 6.5))
    _tube(api, f"{prefix}_MicrophoneCradle",
          [(626, 581, 70), (626, 599, 68), (635, 605, 67), (644, 599, 68), (644, 582, 70)], 1.5)
    _tube(api, f"{prefix}_MicrophoneBand", [(625, 584, 64), (646, 584, 64)], 1.6)
    _tube(api, f"{prefix}_MicrophoneCable",
          [(639, 603, 74), (644, 615, 72), (638, 630, 68), (640, 644, 58)], .8)

    _slab(api, f"{prefix}_ConsoleDesk",
          [(756, 592, 137), (909, 574, 137), (960, 620, 62), (801, 644, 60)], 10)
    for index, corners in enumerate([
        [(797, 650), (805, 649), (805, 668), (797, 670)],
        [(939, 632), (948, 630), (948, 656), (939, 658)],
    ]):
        _rounded(api, f"{prefix}_ConsoleLeg_{index}", corners, 80, 15, 1.5)

    console_quad = [(788, 589, 133), (865, 568, 139), (942, 608, 70), (861, 636, 64)]
    _slab(api, f"{prefix}_MixingConsole", console_quad, 10, "blue")
    _slab(api, f"{prefix}_ConsoleRightCheek",
          [(922, 605, 78), (944, 601, 80), (947, 622, 60), (925, 629, 59)], 8, "gold")
    _monitor(api, f"{prefix}_ConsoleMonitor",
             [(850, 507), (930, 514), (938, 589), (850, 568)], 133,
             [(858, 516), (922, 521), (928, 579), (858, 562)],
             [(895, 577, 134), (895, 588, 122)],
             [(882, 587, 120), (904, 585, 124), (914, 591, 113), (890, 596, 109)])

    knob_positions = [(826, 584), (838, 581), (849, 580), (861, 583),
                      (809, 591), (822, 594), (835, 596), (848, 600),
                      (855, 588), (867, 593), (879, 597), (892, 600),
                      (814, 603), (827, 608), (839, 612), (852, 615)]
    for index, (x, y) in enumerate(knob_positions):
        d = 137 - (y - 580) * 1.45
        _ellipsoid(api, f"{prefix}_ConsoleKnob_{index:02}",
                   (x, y - .8, d - .7), (2, 1.8, 2.7), "gold")
    for index in range(7):
        x, y = 812 + index * 6.1, 607 + index * 1.55
        _tube(api, f"{prefix}_FaderTrack_{index}",
              [(x, y, 96), (x + 5, y + 6, 81)], .55)
        _slab(api, f"{prefix}_FaderCap_{index}",
              [(x + 1, y + 1, 92), (x + 4, y + 1.7, 92),
               (x + 5.2, y + 3.2, 88), (x + 2.2, y + 2.5, 88)], 1.2, "gold")

    _rounded(api, f"{prefix}_SpeakerCabinet",
             [(781, 526), (823, 521), (828, 582), (782, 594)], 127, 29, 2.3)
    _ellipsoid(api, f"{prefix}_SpeakerWoofer", (798, 566, 121), (13.4, 14.8, 7), "gold")
    _ellipsoid(api, f"{prefix}_SpeakerTweeter", (797, 541, 122), (5.9, 6.8, 6))
    _ellipsoid(api, f"{prefix}_SpeakerIndicator", (794, 529, 122), (1.5, 1, 1), "gold")

    chair_outline = [(709, 574), (720, 574), (744, 580), (752, 587),
                     (765, 637), (763, 652), (748, 653), (717, 643),
                     (709, 637), (705, 588)]
    _curved_panel(api, f"{prefix}_ChairBack", chair_outline,
                  lambda u, v: 33 + (652 - v) * .35, 9, 3.5)
    _slab(api, f"{prefix}_ChairSeat",
          [(749, 634, 62), (772, 627, 73), (793, 637, 29), (770, 648, 27)], 5, "pink")
    _tube(api, f"{prefix}_ChairSeatBracket", [(751, 649, 44), (767, 645, 44)], 3.4)
    _tube(api, f"{prefix}_Chair_Mechanism",
          [(747, 659, 39), (753, 651, 42), (769, 642, 48)], 5)
    _wheelbase(api, f"{prefix}_Chair", (747, 674),
               [(718, 678, -2), (731, 687, -12), (772, 682, -7),
                (772, 668, 21), (735, 668, 22)], 30)


def _lower_workspace(api):
    prefix = "Interior_Workspace"
    _slab(api, f"{prefix}_DeskTop",
          [(477, 824, 137), (665, 804, 140), (722, 829, 66), (493, 856, 60)], 10)
    for index, (corners, depth) in enumerate([
        ([(491, 862), (502, 861), (502, 914), (490, 918)], 72),
        ([(701, 846), (713, 845), (713, 900), (700, 904)], 72),
        ([(483, 834), (491, 833), (491, 889), (483, 891)], 132),
    ]):
        _rounded(api, f"{prefix}_DeskLeg_{index}", corners, depth, 11, 1, "gold")
    _rounded(api, f"{prefix}_DeskBackApron",
             [(498, 850), (704, 828), (704, 880), (498, 904)], 133, 12, 1.5)

    _monitor(api, f"{prefix}_LeftMonitor",
             [(491, 746), (580, 737), (582, 810), (491, 819)], 118,
             [(500, 753), (573, 745), (573, 803), (500, 811)],
             [(535, 813, 123), (534, 826, 117)],
             [(517, 827, 117), (543, 823, 123), (553, 830, 100), (522, 834, 96)])
    _monitor(api, f"{prefix}_RightMonitor",
             [(584, 740), (665, 733), (668, 806), (584, 811)], 128,
             [(592, 747), (658, 741), (659, 799), (592, 804)],
             [(622, 807, 132), (622, 817, 123)],
             [(608, 819, 123), (628, 816, 129), (639, 822, 107), (613, 826, 102)])

    keyboard = [(518, 834, 105), (592, 826, 110), (605, 839, 76), (532, 849, 69)]
    _slab(api, f"{prefix}_Keyboard", keyboard, 2.8, "blue")
    _keycaps(api, f"{prefix}_Keyboard", keyboard, 4, 14)
    _ellipsoid(api, f"{prefix}_Mouse", (628, 827, 104), (11, 5.4, 6), "blue")
    _tube(api, f"{prefix}_MouseCable",
          [(625, 823, 111), (622, 819, 125), (618, 819, 130)], .6)

    chair_outline = [(628, 830), (640, 825), (669, 822), (681, 825),
                     (685, 835), (681, 869), (677, 888), (668, 899),
                     (634, 902), (621, 894), (621, 878), (624, 848)]
    _curved_panel(api, f"{prefix}_ChairBack", chair_outline,
                  lambda u, v: 22 + (901 - v) * .34, 10, 3.8)
    _slab(api, f"{prefix}_ChairSeat",
          [(587, 882, 72), (626, 875, 79), (659, 895, 28), (615, 905, 25)], 8, "gold")
    _curved_panel(api, f"{prefix}_LumbarCushion",
                  [(645, 878), (660, 877), (669, 883), (664, 897), (651, 902), (642, 897)],
                  15, 6, 2)
    _tube(api, f"{prefix}_ChairRearBracket",
          [(643, 899, 31), (641, 914, 36)], 4)
    _curved_panel(api, f"{prefix}_ChairLeftArm",
                  [(603, 896), (616, 893), (627, 895), (628, 904), (618, 912), (606, 908)],
                  20, 7, 1.5)
    _wheelbase(api, f"{prefix}_Chair", (635, 922),
               [(607, 925, -2), (621, 935, -12), (662, 929, -6),
                (661, 912, 21), (619, 914, 20)], 29)


def _kitchen(api):
    prefix = "Interior_Kitchen"
    _slab(api, f"{prefix}_CounterTop",
          [(771, 789, 143), (1009, 776, 143), (1056, 793, 65), (779, 814, 59)], 12)
    _rounded(api, f"{prefix}_CabinetBody",
             [(778, 825), (1057, 805), (1057, 879), (779, 903)], 91, 64, 2)
    for name, corners, fill in [
        ("LeftBlueStile", [(779, 827), (813, 824), (813, 898), (779, 902)], "blue"),
        ("RightBlueStile", [(1025, 815), (1056, 812), (1056, 880), (1025, 883)], "blue"),
        ("CenterStile", [(912, 817), (930, 816), (930, 891), (912, 893)], "blue"),
        ("LeftCreamDoor", [(817, 837), (866, 831), (866, 891), (817, 896)], "cream"),
        ("RightCreamDoor", [(868, 831), (912, 827), (912, 888), (868, 891)], "cream"),
    ]:
        _rounded(api, f"{prefix}_{name}", corners, 80, 13, 2.5, fill)
    for index, (top, bottom) in enumerate([(817, 839), (840, 861), (862, 883)]):
        _rounded(api, f"{prefix}_Drawer_{index}",
                 [(935, top + 4), (1024, top - 3), (1024, bottom - 3), (935, bottom + 4)],
                 78, 15, 2)
    for index, (x, y) in enumerate([(875, 843), (892, 841), (977, 829), (977, 850), (977, 872)]):
        _ellipsoid(api, f"{prefix}_Handle_{index}", (x, y, 73), (2.6, 3.6, 3), "blue")
        _tube(api, f"{prefix}_HandleStem_{index}", [(x, y, 73), (x, y, 82)], 1.3)
    for index, x in enumerate([791, 1043]):
        _rounded(api, f"{prefix}_CabinetFoot_{index}",
                 [(x, 888), (x + 8, 887), (x + 8, 902), (x, 903)], 109, 14, 1)

    left_hob = [(774, 789, 137), (878, 783, 140), (927, 798, 87), (800, 811, 74)]
    right_hob = [(916, 780, 140), (991, 779, 140), (1019, 793, 91), (935, 801, 81)]
    _slab(api, f"{prefix}_LeftHob", left_hob, 2.7, "blue")
    _slab(api, f"{prefix}_RightHob", right_hob, 2.7, "blue")
    for index, (x, y, rx, d) in enumerate([
        (799, 789, 15, 130), (823, 801, 15, 92), (884, 793, 19, 107),
        (954, 787, 24, 111), (990, 787, 13, 118),
    ]):
        _revolved(api, f"{prefix}_Burner_{index}", (x, y),
                  [(rx, 0), (rx, 1.2), (rx - 2, 1.4), (rx - 2, 0), (rx, 0)],
                  d, .24, "ink", 32)

    _revolved(api, f"{prefix}_FryingPan", (861, 772),
              [(0, 17), (27, 17), (37, 12), (44, 1), (44, -1),
               (41, -2), (36, 9), (27, 12), (0, 12)],
              95, .24, "blue")
    _revolved(api, f"{prefix}_PanFood", (861, 772),
              [(0, 2.5), (39, 2.5), (36, 9), (0, 9)],
              95, .24, "gold")
    _tube(api, f"{prefix}_PanHandle",
          [(818, 772, 100), (805, 766, 113), (793, 765, 119)], [3.1, 2.7, 2.5])
    _revolved(api, f"{prefix}_CookingPot", (956, 751),
              [(0, 32), (23, 32), (28, 27), (30, 0), (30, -2),
               (27, -3), (25, 25), (21, 27), (0, 27)],
              112, .25, "blue")
    _revolved(api, f"{prefix}_PotLiquid", (956, 751),
              [(0, 1.5), (26, 1.5), (25, 25), (0, 25)],
              112, .25, "blue")
    for index, points in enumerate([
        [(927, 761, 117), (919, 759, 118), (919, 753, 121), (928, 753, 122)],
        [(984, 758, 114), (992, 757, 113), (993, 752, 117), (985, 752, 119)],
    ]):
        _tube(api, f"{prefix}_PotHandle_{index}", points, 1.8)
    _tube(api, f"{prefix}_PotUtensil", [(954, 751, 106), (954, 735, 111)], 2.6)

    _rounded(api, f"{prefix}_WallControls",
             [(1031, 694), (1054, 700), (1054, 757), (1031, 750)], 153, 3, 1.4, "gold")
    for row in range(4):
        for column in range(3):
            x, y = 1037 + column * 5, 709 + row * 9 + column * 1.2
            _ellipsoid(api, f"{prefix}_ControlLamp_{row}_{column}",
                       (x, y, 149), (1.2, 1.8, 1.1), "pink")


def build_interiors(api):
    existing = set(bpy.context.scene.objects)
    _desktop_room(api)
    _recording_room(api)
    _lower_workspace(api)
    _kitchen(api)
    objects = {obj.name: obj for obj in sorted(set(bpy.context.scene.objects) - existing, key=lambda obj: obj.name)
               if obj.type == "MESH"}
    for obj in objects.values():
        _repair_volume(obj)

    for name, obj in objects.items():
        support = None
        if "_Keyboard_Key_" in name:
            support = name.split("_Key_", 1)[0]
        elif name.startswith(("Interior_Recording_ConsoleKnob", "Interior_Recording_Fader")):
            support = "Interior_Recording_MixingConsole"
        elif name.startswith("Interior_Kitchen_ControlLamp"):
            support = "Interior_Kitchen_WallControls"
        elif name == "Interior_Recording_SpeakerIndicator":
            support = "Interior_Recording_SpeakerCabinet"
        elif name.startswith("Interior_Gaming_DriveSlot"):
            support = "Interior_Gaming_ComputerCase"
        if support:
            _seat_detail(obj, objects[support])

    _mount_wall_fixtures(api, objects)

    connections = []
    for prefix, count, top_name, leg_name in (
        ("Interior_Gaming", 2, "DeskTop", "DeskLeg"),
        ("Interior_Recording", 2, "ConsoleDesk", "ConsoleLeg"),
        ("Interior_Workspace", 3, "DeskTop", "DeskLeg"),
    ):
        top = objects[f"{prefix}_{top_name}"]
        for index in range(count):
            leg = objects[f"{prefix}_{leg_name}_{index}"]
            _extend_support_to_top(leg, top)
            connections.append((leg.name, top.name, 3.5))
    _extend_support_to_top(objects["Interior_Workspace_DeskBackApron"],
                           objects["Interior_Workspace_DeskTop"])
    _extend_support_to_top(objects["Interior_Kitchen_CabinetBody"],
                           objects["Interior_Kitchen_CounterTop"])

    for prefix in ("Interior_Gaming", "Interior_Recording", "Interior_Workspace"):
        connections.append((f"{prefix}_ChairBack", f"{prefix}_ChairSeat", 4))
    for prefix, monitor, top in (
        ("Interior_Gaming", "MainMonitor", "DeskTop"),
        ("Interior_Recording", "ConsoleMonitor", "MixingConsole"),
        ("Interior_Workspace", "LeftMonitor", "DeskTop"),
        ("Interior_Workspace", "RightMonitor", "DeskTop"),
    ):
        for first, second in (("Housing", "Stand"), ("Stand", "Foot")):
            connections.append((f"{prefix}_{monitor}_{first}", f"{prefix}_{monitor}_{second}", 3))
        connections.append((f"{prefix}_{monitor}_Foot", f"{prefix}_{top}", 3))

    connections += [
        ("Interior_Gaming_ChairLeftArm", "Interior_Gaming_ChairBack", 2),
        ("Interior_Gaming_ChairLeftArm", "Interior_Gaming_ChairSeat", 2.5),
        ("Interior_Gaming_ChairRightArmUpright", "Interior_Gaming_ChairSeat", 2.5),
        ("Interior_Gaming_ChairRightArmPad", "Interior_Gaming_ChairRightArmUpright", 2.5),
        ("Interior_Gaming_ComputerCase", "Interior_Gaming_DeskTop", 4),
        ("Interior_Gaming_MouseMat", "Interior_Gaming_DeskTop", 2),
        ("Interior_Gaming_Mouse", "Interior_Gaming_MouseMat", 2),
        ("Interior_Gaming_Keyboard", "Interior_Gaming_DeskTop", 3),
        ("Interior_Recording_Chair_Mechanism", "Interior_Recording_ChairSeat", 4),
        ("Interior_Recording_Chair_Mechanism", "Interior_Recording_Chair_GasLift", 4),
        ("Interior_Recording_SpeakerCabinet", "Interior_Recording_ConsoleDesk", 4),
        ("Interior_Recording_MixingConsole", "Interior_Recording_ConsoleDesk", 4),
        ("Interior_Recording_ConsoleRightCheek", "Interior_Recording_MixingConsole", 3),
        ("Interior_Recording_LampStem", "Interior_Recording_LampShade", 3),
        ("Interior_Recording_LampBulb", "Interior_Recording_LampShade", 2),
        ("Interior_Workspace_ChairLeftArm", "Interior_Workspace_ChairSeat", 3),
        ("Interior_Workspace_LumbarCushion", "Interior_Workspace_ChairBack", 2),
        ("Interior_Workspace_ChairRearBracket", "Interior_Workspace_ChairSeat", 3),
        ("Interior_Workspace_Mouse", "Interior_Workspace_DeskTop", 2),
        ("Interior_Workspace_Keyboard", "Interior_Workspace_DeskTop", 3),
        ("Interior_Workspace_DeskBackApron", "Interior_Workspace_DeskTop", 4),
        ("Interior_Kitchen_CabinetBody", "Interior_Kitchen_CounterTop", 5),
        ("Interior_Kitchen_LeftHob", "Interior_Kitchen_CounterTop", 3),
        ("Interior_Kitchen_RightHob", "Interior_Kitchen_CounterTop", 3),
        ("Interior_Kitchen_FryingPan", "Interior_Kitchen_LeftHob", 8),
        ("Interior_Kitchen_CookingPot", "Interior_Kitchen_RightHob", 8),
        ("Interior_Kitchen_FryingPan", "Interior_Kitchen_PanHandle", 2.5),
        ("Interior_Kitchen_CookingPot", "Interior_Kitchen_PotHandle_0", 2),
        ("Interior_Kitchen_CookingPot", "Interior_Kitchen_PotHandle_1", 2),
    ]
    for name in objects:
        if name.startswith("Interior_Recording_ConsoleKnob"):
            connections.append((name, "Interior_Recording_MixingConsole", 1.3))
        elif name.startswith("Interior_Recording_FaderCap"):
            connections.append((name, "Interior_Recording_MixingConsole", 1))
        elif name.startswith("Interior_Kitchen_Burner"):
            hob = "LeftHob" if int(name.rsplit("_", 1)[1]) < 3 else "RightHob"
            connections.append((name, f"Interior_Kitchen_{hob}", 2))
    for first, second, radius in connections:
        _connect_parts(api, f"{first}_MountTo_{second.rsplit('_', 1)[-1]}",
                       objects[first], objects[second], radius,
                       objects[first].get("sourceFill", "blue"))

    _seat_floor_supports(api, objects)

    rounded_parts = ("ChairBack", "Lumbar", "ArmPad", "Mouse", "Cone", "Tweeter",
                     "Woofer", "Fan", "Figurine", "Caster", "Hub", "Knob",
                     "MicrophoneBody", "MicrophoneBase", "LampShade", "LampBulb",
                     "FryingPan", "CookingPot", "PotLiquid", "PanFood", "Burner", "Handle")
    for obj in sorted(set(bpy.context.scene.objects) - existing, key=lambda obj: obj.name):
        if obj.type != "MESH":
            continue
        _repair_volume(obj)
        if any(part in obj.name for part in rounded_parts):
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
        uv = obj.data.uv_layers.active
        for polygon in obj.data.polygons:
            source = obj.data.materials[polygon.material_index].name.startswith("source")
            for loop_index in polygon.loop_indices:
                position = obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
                uv.data[loop_index].uv = ((position.x / 1536, position.z / 1024) if source
                                           else (position.x / 110, (1024 - position.z) / 110))
