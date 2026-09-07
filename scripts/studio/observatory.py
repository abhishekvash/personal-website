"""Closed observatory shell and supported optical and rooftop assemblies."""

import json
import math

import bmesh
from mathutils import Vector

from common import rounded_quad, triangulate


CENTER_U = 729.0
TILT = 5.0 / 140.0
SEGMENTS = 128


def smooth_contour(points, steps=8):
    result = []
    for index, p1 in enumerate(points):
        p0, p2, p3 = points[index - 1], points[(index + 1) % len(points)], points[(index + 2) % len(points)]
        for step in range(steps):
            t = step / steps
            result.append(tuple(.5 * ((2 * p1[axis]) + (-p0[axis] + p2[axis]) * t
                                      + (2 * p0[axis] - 5 * p1[axis] + 4 * p2[axis] - p3[axis]) * t * t
                                      + (-p0[axis] + 3 * p1[axis] - 3 * p2[axis] + p3[axis]) * t * t * t)
                                for axis in range(2)))
    return result


def _center_depth(u):
    return 200 - .2 * (u - CENTER_U)


class _DomeProfile:
    def __init__(self, base, height, radius, depth_radius, cylinder, back_lift):
        self.base, self.height, self.radius = base, height, radius
        self.depth_radius, self.cylinder, self.back_lift = depth_radius, cylinder, back_lift

    def radius_at(self, u, v):
        height = self.base - v + TILT * (u - CENTER_U)
        cap = max(0, height - self.cylinder) / (self.height - self.cylinder)
        return self.radius * math.sqrt(max(0, 1 - cap * cap)), height

    def inside(self, u, v):
        radius, height = self.radius_at(u, v)
        return 0 <= height <= self.height and abs(u - CENTER_U) <= radius

    def position(self, u, v, back=False, silhouette=False):
        radius, height = self.radius_at(u, v)
        fraction = math.sqrt(max(0, 1 - ((u - CENTER_U) / max(radius, 1e-8)) ** 2))
        radial = fraction * radius / self.radius
        if silhouette and height > 1e-5:
            radial = 0
        depth = _center_depth(u) + self.depth_radius * radial * (1 if back else -1)
        if back:
            v -= self.back_lift * radial * max(0, 1 - height / 72)
        return u, v, depth

    def boundary(self, origin, direction):
        low, high = 0.0, 700.0
        for _ in range(55):
            distance = (low + high) * .5
            if self.inside(origin[0] + direction[0] * distance, origin[1] + direction[1] * distance):
                low = distance
            else:
                high = distance
        return origin[0] + direction[0] * low, origin[1] + direction[1] * low

    def floor_depth(self, u, v):
        radial = math.sqrt(max(0, 1 - ((u - CENTER_U) / self.radius) ** 2))
        front = _center_depth(u) - self.depth_radius * radial
        depth = front + (self.base + TILT * (u - CENTER_U) - v) * 2 * self.depth_radius / self.back_lift
        assert front - 1e-4 <= depth <= _center_depth(u) + self.depth_radius * radial + 1e-4
        return depth


OUTER = _DomeProfile(239, 200, 140, 110, 64, 20)
INNER = _DomeProfile(215, 164, 128, 98, 40, 24)


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _ray_contour(points, origin, direction):
    hits = []
    for first, second in zip(points, points[1:] + points[:1]):
        edge = (second[0] - first[0], second[1] - first[1])
        delta = (first[0] - origin[0], first[1] - origin[1])
        denominator = _cross(direction, edge)
        if abs(denominator) < 1e-10:
            continue
        distance = _cross(delta, edge) / denominator
        along = _cross(delta, direction) / denominator
        if distance > 0 and -.000001 <= along <= 1.000001:
            hits.append(distance)
    if not hits:
        raise ValueError("An optical aperture ray missed its contour.")
    distance = min(hits)
    return origin[0] + distance * direction[0], origin[1] + distance * direction[1]


class _ShellMesh:
    def __init__(self):
        self.vertices, self.faces, self.groups = [], [], {}

    def vertex(self, point):
        self.vertices.append(point)
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
            after = (index + 1) % len(first)
            self.face((first[index], first[after], second[after], second[index]), label, fill)

    def body(self, profile, aperture, label, fill):
        origin = (770, 144)
        directions = [(math.cos(index * math.tau / SEGMENTS), math.sin(index * math.tau / SEGMENTS)) for index in range(SEGMENTS)]
        contour = [profile.boundary(origin, direction) for direction in directions]
        previous, aperture_indices = None, None
        bands = 18
        for step in range(bands + 1):
            t = step / bands
            points = [((1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1]) for a, b in zip(aperture, contour)]
            current = [self.vertex(profile.position(u, v, silhouette=step == bands)) for u, v in points]
            if previous is not None:
                self.bridge(previous, current, f"{label} front", fill)
            else:
                aperture_indices = current
            previous = current
        front_boundary = previous
        back_boundary = []
        for index, (u, v) in enumerate(contour):
            _, height = profile.radius_at(u, v)
            if height > 1e-5:
                back_boundary.append(front_boundary[index])
            else:
                back_boundary.append(self.vertex(profile.position(u, v, back=True, silhouette=True)))
        center = self.vertex(profile.position(*origin, back=True))
        previous = None
        for step in range(1, bands + 1):
            t = step / bands
            current = back_boundary if step == bands else [
                self.vertex(profile.position(origin[0] * (1 - t) + u * t, origin[1] * (1 - t) + v * t, back=True))
                for u, v in contour
            ]
            if previous is None:
                for index in range(SEGMENTS):
                    self.face((center, current[index], current[(index + 1) % SEGMENTS]), f"{label} rear", fill)
            else:
                self.bridge(previous, current, f"{label} rear", fill)
            previous = current
        self.bridge(front_boundary, back_boundary, f"{label} floor", fill)
        return aperture_indices

    def finish(self, api, name):
        obj = api.mesh(name, self.vertices, self.faces)
        obj["sourceFill"] = "cream"
        obj["surfaceGroups"] = json.dumps(self.groups)
        _close_normals(obj)
        return obj


def _close_normals(obj, weld=False):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    if weld:
        bmesh.ops.remove_doubles(mesh, verts=list(mesh.verts), dist=1e-5)
    bmesh.ops.recalc_face_normals(mesh, faces=list(mesh.faces))
    mesh.to_mesh(obj.data)
    mesh.free()
    obj.data.update()


def _ellipsoid(api, name, center, radii, fill):
    obj = api.ellipsoid(name, center, radii)
    obj["sourceFill"] = fill
    _close_normals(obj, weld=True)
    return obj


def _build_shell(api):
    outer = smooth_contour([(746,57),(776,60),(806,77),(834,107),(848,142),(850,171),(841,199),(820,218),(792,226),(762,221),(733,203),(709,177),(695,150),(689,116),(696,87),(719,67)])
    inner = smooth_contour([(746,77),(770,78),(796,91),(818,115),(833,143),(835,169),(825,191),(808,205),(783,211),(758,203),(734,187),(716,164),(707,139),(705,113),(711,94),(726,82)])
    origin = (770, 144)
    directions = [(math.cos(index * math.tau / SEGMENTS), math.sin(index * math.tau / SEGMENTS)) for index in range(SEGMENTS)]
    outer = [_ray_contour(outer, origin, direction) for direction in directions]
    inner = [_ray_contour(inner, origin, direction) for direction in directions]
    if not all(OUTER.inside(*point) for point in outer) or not all(INNER.inside(*point) for point in inner):
        raise ValueError("The optical aperture extends beyond its structural shell.")
    builder = _ShellMesh()
    outer_boundary = builder.body(OUTER, outer, "Exterior shell", "cream")
    inner_boundary = builder.body(INNER, inner, "Interior chamber", "ink")
    front_outer = [builder.vertex((u, v, _center_depth(u) - 125)) for u, v in outer]
    front_inner = [builder.vertex((u, v, _center_depth(u) - 125)) for u, v in inner]
    builder.bridge(outer_boundary, front_outer, "Raised rim outer wall", "cream")
    builder.bridge(front_outer, front_inner, "Optical rim front", "cream")
    builder.bridge(front_inner, inner_boundary, "Optical aperture tunnel", "ink")
    shell = builder.finish(api, "Observatory • continuous shell and optical aperture")
    for group_name, group in builder.groups.items():
        smooth = group_name.endswith("front") or group_name.endswith("rear")
        if group_name == "Optical rim front":
            smooth = False
        for index in group["faces"]:
            shell.data.polygons[index].use_smooth = smooth
    return shell


def _roof_support(u, v):
    from architecture import roof_depth
    return min(330, roof_depth(u, v))


def _roof_height(u, depth):
    from architecture import ROOF_BACK, ROOF_FRONT, plane_depth
    outline = [*ROOF_FRONT, *reversed(ROOF_BACK)]
    triangles = triangulate([[Vector((x, y, 0)) for x, y, _ in outline]])
    choices = [plane_depth(u, depth, [(outline[i][0], outline[i][2], outline[i][1]) for i in triangle])
               for triangle in triangles]
    height, containment = max(choices, key=lambda choice: choice[1])
    if containment < -.00001:
        raise ValueError(f"Observatory collar extends beyond its roof support at {(u, depth)}")
    return height


def _closed_loft(api, name, top, bottom, fill="blue", bottom_sampler=None):
    count = len(top)
    vertices = top + bottom
    top_center = tuple(sum(point[axis] for point in top) / count for axis in range(3))
    bottom_center = tuple(sum(point[axis] for point in bottom) / count for axis in range(3))
    if bottom_sampler:
        bottom_center = (*bottom_center[:2], bottom_sampler(*bottom_center[:2]))
    vertices += [top_center, bottom_center]
    faces, groups = [], {}

    def face(indices, label):
        groups.setdefault(label, {"faces": [], "fill": fill})["faces"].append(len(faces))
        faces.append(indices)

    for index in range(count):
        after = (index + 1) % count
        face((count * 2, index, after), "Top")
        face((index, index + count, after + count, after), "Outer sides")
    if bottom_sampler:
        previous = None
        bands = 16 if count > 32 else 8
        for step in range(1, bands + 1):
            ratio = step / bands
            current = []
            for index, point in enumerate(bottom):
                if step == bands:
                    current.append(index + count)
                    continue
                u, v = (bottom_center[axis] * (1 - ratio) + point[axis] * ratio for axis in range(2))
                current.append(len(vertices))
                vertices.append((u, v, bottom_sampler(u, v)))
            for index in range(count):
                after = (index + 1) % count
                if previous is None:
                    face((count * 2 + 1, current[after], current[index]), "Supported underside")
                else:
                    face((previous[index], previous[after], current[after], current[index]), "Supported underside")
            previous = current
    else:
        for index in range(count):
            face((count * 2 + 1, (index + 1) % count + count, index + count), "Supported underside")
    obj = api.mesh(name, vertices, faces)
    obj["sourceFill"] = fill
    obj["surfaceGroups"] = json.dumps(groups)
    _close_normals(obj)
    return obj


def _build_collar(api):
    top = []
    for index in range(SEGMENTS):
        angle = index * math.tau / SEGMENTS
        cosine, sine = math.cos(angle), math.sin(angle)
        u = 730 + 151 * cosine
        top.append((u, 237 + 5 * cosine + min(0, 20 * sine), _center_depth(u) - 124 * sine))
    center = tuple(sum(point[axis] for point in top) / SEGMENTS for axis in range(3))
    builder = _ShellMesh()
    boundaries = []
    for underside in (False, True):
        center_v = _roof_height(center[0], center[2]) if underside else center[1]
        center_index = builder.vertex((center[0], center_v, center[2]))
        previous = None
        label = "Roof contact underside" if underside else "Raised collar top"
        for band in range(1, 17):
            ratio = band / 16
            current = []
            for point in top:
                u, v, depth = (center[axis] * (1 - ratio) + point[axis] * ratio for axis in range(3))
                support_v = _roof_height(u, depth)
                if support_v <= v:
                    raise ValueError("Observatory collar top intersects its roof support.")
                current.append(builder.vertex((u, support_v if underside else v, depth)))
            if previous is None:
                for index in range(SEGMENTS):
                    builder.face((center_index, current[index], current[(index + 1) % SEGMENTS]), label, "blue")
            else:
                builder.bridge(previous, current, label, "blue")
            previous = current
        boundaries.append(previous)
    builder.bridge(*boundaries, "Collar outer wall", "blue")
    collar = builder.finish(api, "Observatory • solid supported base collar")
    collar["sourceFill"] = "blue"
    return collar


def _surface_depth(surface, u, v):
    candidates = []
    center = tuple(sum(point[axis] for point in surface) / len(surface) for axis in range(3))
    for index, second in enumerate(surface):
        first, third = center, surface[(index + 1) % len(surface)]
        edge1 = (second[0] - first[0], second[1] - first[1])
        edge2 = (third[0] - first[0], third[1] - first[1])
        delta = (u - first[0], v - first[1])
        denominator = _cross(edge1, edge2)
        a, b = _cross(delta, edge2) / denominator, _cross(edge1, delta) / denominator
        depth = first[2] + a * (second[2] - first[2]) + b * (third[2] - first[2])
        candidates.append((min(a, b, 1 - a - b), depth))
    return max(candidates)[1]


def _pedestal(api, name, top_outline, bottom_outline, support, fill="blue", planar_top=False):
    bottom = [(u, v, support(u, v)) for u, v in bottom_outline]
    top = [(u, v, point[2]) for (u, v), point in zip(top_outline, bottom)]
    if planar_top:
        plane = top[:3]
        top = [(u, v, _surface_depth(plane, u, v)) for u, v, _ in top]
    _closed_loft(api, name, top, bottom, fill, bottom_sampler=support)
    return top


def _build_roof_fittings(api):
    platform = _pedestal(api, "Observatory • supported antenna platform",
                         [(500,253),(534,243),(584,260),(545,273)],
                         [(497,270),(534,260),(584,277),(545,285)], _roof_support)
    foot = _pedestal(api, "Observatory • antenna foot",
                     [(526,237),(547,232),(567,242),(545,251)],
                     [(525,251),(547,249),(567,258),(545,265)],
                     lambda u, v: _surface_depth(platform, u, v))
    column = _pedestal(api, "Observatory • antenna column",
                       [(538,200),(548,196),(558,199),(548,203)],
                       [(538,241),(548,244),(558,241),(548,238)],
                       lambda u, v: _surface_depth(foot, u, v), "cream")
    depth = _surface_depth(column, 549, 202)
    api.tube("Observatory • antenna aerial", [(549,173,depth),(549,202,depth)], 1.7, "blue", True)
    chimney = _pedestal(api, "Observatory • supported chimney",
                        [(879,201),(893,198),(910,202),(894,207)],
                        [(877,257),(893,252),(911,257),(894,265)], _roof_support, "cream", planar_top=True)
    cap_top, cap_bottom = [], []
    for index in range(48):
        angle = index * math.tau / 48
        u, v = 895 + 15 * math.cos(angle), 202 + 5 * math.sin(angle)
        depth = _surface_depth(chimney, u, v)
        cap_top.append((u, v - 2, depth))
        cap_bottom.append((u, v + .5, depth))
    _closed_loft(api, "Observatory • seated chimney cap", cap_top, cap_bottom, "cream")


def _build_telescope(api):
    def depth(u, extra=0):
        return 164 - .2 * (u - 770) + extra
    barrel = [(739,122,depth(739,-3)),(752,128,depth(752)),(770,139,depth(770,3)),
              (790,147,depth(790,7)),(811,159,depth(811,10))]
    api.tube("Observatory • telescope optical barrel", barrel, [12,12,10,9,7], "gold", True)
    for index, (u, v, radius, offset) in enumerate([(740,122,12, -3),(754,129,11,0),(775,141,10,4),(794,149,9,8),(811,159,8,10)]):
        api.tube(f"Observatory • telescope connected band {index+1}",
                 [(u-1.3,v-.7,depth(u-1.3,offset)),(u+1.3,v+.7,depth(u+1.3,offset))], radius+.8, "gold", True)
    _ellipsoid(api, "Observatory • telescope lens", (736,120,depth(736,-8)), (6,10,4), "ink")
    pivot = (774,174,depth(774,3))
    api.tube("Observatory • connected telescope mount", [(774,148,depth(774,3)),pivot], 5, "gold", True)
    _ellipsoid(api, "Observatory • tripod head", pivot, (7,5,7), "gold")
    for index, (u, v) in enumerate([(751,202),(780,210),(799,199)]):
        foot = (u, v, INNER.floor_depth(u, v))
        api.tube(f"Observatory • floor seated tripod leg {index+1}", [pivot,foot], 3, "gold", True)
        _ellipsoid(api, f"Observatory • tripod contact pad {index+1}", foot, (4,2,4), "gold")


def _build_shell_fittings(api):
    cap = rounded_quad([(694,46),(706,33),(729,29),(757,30),(775,36),(775,48),(753,45),(718,48)], 2, 4)
    # The raised top fitting reaches down onto the dome; its painted silhouette stays fixed.
    cap_front = [(u, v, _center_depth(u) - 15) for u, v in cap]
    cap_back = [(u, v + 14, _center_depth(u) + 12) for u, v in cap]
    _closed_loft(api, "Observatory • seated crown fitting", cap_front, cap_back)
    rail = [(598,135),(620,85),(665,55),(698,40),(699,46),(668,59),(625,91),(603,140)]
    rail_surface = [OUTER.position(u, v) for u, v in rail]
    rail_front = [(u, v, depth - 2) for u, v, depth in rail_surface]
    rail_back = [(u, v, depth + 4) for u, v, depth in rail_surface]
    count = len(rail)
    triangles = triangulate([[Vector((u, v, 0)) for u, v in rail]])
    faces = list(triangles) + [tuple(index + count for index in reversed(face)) for face in triangles]
    faces += [(index, (index + 1) % count, (index + 1) % count + count, index + count) for index in range(count)]
    rail_object = api.mesh("Observatory • mounted roof rail", rail_front + rail_back, faces)
    rail_object["sourceFill"] = "blue"
    _close_normals(rail_object)
    door = rounded_quad([(628,191),(657,193),(659,230),(628,231)], 5)
    outside = [OUTER.position(u, v) for u, v in door]
    door_front = [(u, v, depth - 2) for u, v, depth in outside]
    door_back = [(u, v, depth + 3) for u, v, depth in outside]
    _closed_loft(api, "Observatory • mounted service door", door_front, door_back)


def build_observatory(api):
    _build_shell(api)
    _build_collar(api)
    _build_telescope(api)
    _build_roof_fittings(api)
    _build_shell_fittings(api)
