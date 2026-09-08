"""Image-matched, volumetric flowering bonsai and ceramic planter."""

import math
import heapq

import numpy as np

from common import HEIGHT, WIDTH


def _material_faces(api, obj, back_material, indices):
    obj.data.materials.append(api.material(back_material))
    for index in indices:
        obj.data.polygons[index].material_index = 1


def _smooth_samples(values, passes=2):
    values = np.asarray(values, dtype=float)
    for _ in range(passes):
        padded = np.pad(values, ((2, 2),) + ((0, 0),) * (values.ndim - 1), mode="edge")
        values = sum(padded[index:index + len(values)] * weight for index, weight in enumerate((1, 4, 6, 4, 1))) / 16
    return values


def _close_silhouette(mask, radius=9):
    """Ignore grain-sized holes when fitting wood, while retaining large gaps."""
    result = mask.copy()
    for operation in (np.logical_or.reduce, np.logical_and.reduce):
        for _ in range(radius):
            padded = np.pad(result, 1)
            result = operation((padded[1:-1, 1:-1], padded[:-2, 1:-1], padded[2:, 1:-1], padded[1:-1, :-2], padded[1:-1, 2:]))
    return result


def _tapered_branch(api, name, points, radii, material="bark", sides=16, ownership=None, stable_sections=False):
    """Continuous smooth tube fitted to the broad silhouette, not ink noise."""
    dense_points, dense_radii = [], []
    for index in range(len(points) - 1):
        first, last = np.asarray(points[index]), np.asarray(points[index + 1])
        count = max(1, math.ceil(np.linalg.norm(last - first) / 4))
        for sample in range(count):
            fraction = sample / count
            dense_points.append(first * (1 - fraction) + last * fraction)
            dense_radii.append(radii[index] * (1 - fraction) + radii[index + 1] * fraction)
    dense_points.append(points[-1])
    dense_radii.append(radii[-1])
    points = np.asarray(dense_points, dtype=float)
    radii = _smooth_samples(dense_radii)
    points = _smooth_samples(points)
    vertices = []
    faces = []
    back_faces = []

    def inside(u, v):
        if ownership is None:
            return True
        x, y = round(u), round(v)
        return 0 <= y < ownership.shape[0] and 0 <= x < ownership.shape[1] and ownership[y, x]

    if ownership is not None:
        adjusted = points.copy()
        for index, point in enumerate(points):
            if inside(point[0], point[1]):
                continue
            x, y = round(point[0]), round(point[1])
            left, top = max(0, x - 28), max(0, y - 28)
            right, bottom = min(ownership.shape[1], x + 29), min(ownership.shape[0], y + 29)
            candidates_y, candidates_x = np.where(ownership[top:bottom, left:right])
            if len(candidates_x):
                nearest = np.argmin((candidates_x + left - point[0]) ** 2 + (candidates_y + top - point[1]) ** 2)
                adjusted[index, :2] = (candidates_x[nearest] + left, candidates_y[nearest] + top)
        points = _smooth_samples(adjusted, passes=3)

    normals, binormals = [], []
    positive, negative = radii.copy(), radii.copy()
    axis = points[-1] - points[0]
    for index, point in enumerate(points):
        tangent = points[min(index + 1, len(points) - 1)] - points[max(index - 1, 0)]
        tangent /= max(np.linalg.norm(tangent), 0.001)
        normal = np.array([-axis[1], axis[0], 0.0]) if stable_sections else np.array([-tangent[1], tangent[0], 0.0])
        if np.linalg.norm(normal) < 0.001:
            normal = np.array([1.0, 0.0, 0.0])
        normal /= np.linalg.norm(normal)
        # Wide, tightly bent trunks use parallel sections so their inner rings
        # cannot fold through one another. The centerline still twists in depth.
        binormal = np.array([0.0, 0.0, 1.0]) if stable_sections else np.cross(tangent, normal)
        normals.append(normal)
        binormals.append(binormal)
        if ownership is not None:
            for sign, envelope in ((1, positive), (-1, negative)):
                allowed = 0.0
                for distance in np.arange(0.5, radii[index] + 0.5, 0.5):
                    if not inside(*(point[:2] + normal[:2] * distance * sign)):
                        break
                    allowed = distance
                envelope[index] = max(allowed, radii[index] * 0.28, 0.7)
    # Longitudinal smoothing is performed once on the envelope. Individual
    # surface vertices are never snapped or cut at printed flecks and holes.
    positive = _smooth_samples(positive, passes=5)
    negative = _smooth_samples(negative, passes=5)
    for index, point in enumerate(points):
        normal, binormal = normals[index], binormals[index]
        for side in range(sides):
            angle = 2 * math.pi * side / sides
            cross_radius = positive[index] if math.cos(angle) >= 0 else negative[index]
            offset = normal * math.cos(angle) * cross_radius
            offset += binormal * math.sin(angle) * radii[index]
            vertices.append(tuple(point + offset))
    for ring in range(len(points) - 1):
        for side in range(sides):
            a = ring * sides + side
            b = ring * sides + (side + 1) % sides
            if math.sin(2 * math.pi * (side + 0.5) / sides) > 0:
                back_faces.append(len(faces))
            faces.append((a, b, b + sides, a + sides))
    back_faces.append(len(faces))
    faces.append(tuple(range(sides - 1, -1, -1)))
    back_faces.append(len(faces))
    faces.append(tuple((len(points) - 1) * sides + i for i in range(sides)))
    obj = api.mesh(name, vertices, faces, material=material)
    obj["sourceFill"] = "bark"
    if material == "source":
        # Only the camera-facing half of each branch receives owned artwork.
        _material_faces(api, obj, "bark", back_faces)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return points, radii, positive, negative


def _branch_depth_field(surfaces, shape, offset, step):
    """Continuous front/back bark depths from the real supporting tubes."""
    rows, columns = shape
    yy, xx = np.indices((rows + 1, columns + 1), dtype=float)
    xx = offset[0] + xx * step - 0.5
    yy = offset[1] + yy * step - 0.5
    front = np.full(xx.shape, np.inf)
    back = np.zeros(xx.shape)
    nearest = np.full(xx.shape, np.inf)
    covered = np.zeros(xx.shape, dtype=bool)
    for points, radii, positive, negative in surfaces:
        selected = list(range(0, len(points), 3))
        if selected[-1] != len(points) - 1:
            selected.append(len(points) - 1)
        for first_index, last_index in zip(selected[:-1], selected[1:]):
            first, last = points[first_index], points[last_index]
            delta = last - first
            length = max(float(delta[0] ** 2 + delta[1] ** 2), 0.001)
            fraction = np.clip(((xx - first[0]) * delta[0] + (yy - first[1]) * delta[1]) / length, 0, 1)
            cx = first[0] + delta[0] * fraction
            cy = first[1] + delta[1] * fraction
            depth = first[2] + delta[2] * fraction
            signed = ((xx - cx) * -delta[1] + (yy - cy) * delta[0]) / math.sqrt(length)
            positive_radius = positive[first_index] * (1 - fraction) + positive[last_index] * fraction
            negative_radius = negative[first_index] * (1 - fraction) + negative[last_index] * fraction
            width = np.where(signed >= 0, positive_radius, negative_radius)
            depth_radius = radii[first_index] * (1 - fraction) + radii[last_index] * fraction
            distance = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            inside = distance <= width
            candidate = depth - depth_radius * np.sqrt(np.maximum(0, 1 - (distance / np.maximum(width, 0.1)) ** 2)) - 0.7
            gap = distance - width
            use = (inside & (~covered | (candidate < front))) | (~inside & ~covered & (gap < nearest))
            front[use] = candidate[use]
            back[use] = np.maximum(candidate[use] + 4, depth[use] + depth_radius[use] * 0.6)
            nearest[use] = gap[use]
            covered |= inside
    return front, back


def _flower_and_bark_masks(pixels):
    """Classify visible ink, retaining independent flower and wood surfaces."""
    rgb = pixels[:675, 930:1536, :3].astype(np.float32)
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    pink = (red > 130) & (red > green * 1.16) & (red > blue * 1.10)
    pink &= (green < 211) & (blue > green - (red - green) * 0.4)
    # Pale printed highlights belong to a blossom only when surrounded by pink.
    neighbors = np.zeros(pink.shape, dtype=np.uint8)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        shifted = np.roll(pink, (dy, dx), axis=(0, 1))
        if dy < 0:
            shifted[-1] = False
        elif dy > 0:
            shifted[0] = False
        if dx < 0:
            shifted[:, -1] = False
        elif dx > 0:
            shifted[:, 0] = False
        neighbors += shifted
    blue_ink = (blue > red * 1.07) & (green < 183)
    pink |= (neighbors >= 3) & (red > 190)
    # Grain and pale petal centers are surface print, not holes through flowers.
    # Preserve branch-colored gaps while joining tiny breaks inside rose ink.
    pink |= _close_silhouette(pink, radius=2) & (red > 170) & ~blue_ink
    yy, xx = np.indices(pink.shape)
    xx = xx + 930
    trunk_region = (
        (yy > 365)
        & (xx > 1150)
        & (xx < 1405)
        & (xx > 1160 + np.maximum(0, yy - 440) * 0.32)
    )
    golden_bark = (red < 229) & (green < 185) & (blue < 144)
    golden_bark &= (red > green * 1.035) & trunk_region
    bark = (blue_ink | golden_bark) & ~pink
    # The crop includes part of the studio; its blue panels are not tree bark.
    studio_boundary = np.where(yy < 245, 930, np.where(yy < 445, 1029, np.where(yy < 634, 1085, 1109)))
    bark &= xx >= studio_boundary
    pink &= ~((xx < 982) & (yy > 273))
    # The planter is constructed separately and must not become branch geometry.
    bark[590:] &= (xx[590:] > 1238) & (xx[590:] < 1385)
    pink[(yy > 602) & (xx > 1138) & (xx < 1484)] = False
    pink[635:] = False
    return pink, bark


def _connected_contours(mask, offset, step):
    """Keep each connected printed petal or flower cluster as one surface."""
    labels = np.full(mask.shape, -1, dtype=np.int32)
    centers = {}
    spans = {}
    rows, columns = mask.shape
    for row, column in zip(*np.where(mask)):
        if labels[row, column] >= 0:
            continue
        label = len(centers)
        labels[row, column] = label
        pending = [(int(row), int(column))]
        coordinates = []
        while pending:
            y, x = pending.pop()
            coordinates.append((x, y))
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < rows and 0 <= nx < columns and mask[ny, nx] and labels[ny, nx] < 0:
                    labels[ny, nx] = label
                    pending.append((ny, nx))
        coordinates = np.asarray(coordinates, dtype=float)
        center = coordinates.mean(axis=0) * step + np.asarray(offset) + 0.5
        variation = math.sin(label * 2.399963)
        centers[label] = (center[0], center[1], variation)
        span = np.maximum(4, (np.ptp(coordinates, axis=0) + 1) * step * 0.5)
        spans[label] = (span[0], span[1])
    return labels, centers, spans


def _contour_distance(mask):
    distance = np.zeros(mask.shape, dtype=np.float32)
    inside = mask.copy()
    while inside.any():
        distance[inside] += 1
        padded = np.pad(inside, 1)
        inside = np.logical_and.reduce((padded[1:-1, 1:-1], padded[:-2, 1:-1], padded[2:, 1:-1], padded[1:-1, :-2], padded[1:-1, 2:]))
    return distance


def _flower_contours(mask, offset, step):
    """Separate touching flowers at their natural narrow joins, without a grid."""
    distance = _contour_distance(mask)
    padded = np.pad(distance, 1)
    neighbors = np.maximum.reduce([padded[dy:dy + mask.shape[0], dx:dx + mask.shape[1]] for dy in range(3) for dx in range(3)])
    seeds = (distance >= 2) & (distance >= neighbors)
    labels, centers, _ = _connected_contours(seeds, offset, step)
    pending = []
    sequence = 0
    rows, columns = mask.shape
    for row, column in zip(*np.where(seeds)):
        heapq.heappush(pending, (-float(distance[row, column]), sequence, int(row), int(column), int(labels[row, column])))
        sequence += 1
    while pending:
        _, _, y, x, label = heapq.heappop(pending)
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < rows and 0 <= nx < columns and mask[ny, nx] and labels[ny, nx] < 0:
                labels[ny, nx] = label
                heapq.heappush(pending, (-float(distance[ny, nx]), sequence, ny, nx, label))
                sequence += 1
    small_labels, _, _ = _connected_contours(mask & (labels < 0), offset, step)
    small = small_labels >= 0
    labels[small] = small_labels[small] + len(centers)
    centers, spans = {}, {}
    for label in np.unique(labels[mask]):
        ys, xs = np.where(labels == label)
        centers[int(label)] = (offset[0] + xs.mean() * step + 0.5, offset[1] + ys.mean() * step + 0.5, math.sin(int(label) * 2.399963))
        spans[int(label)] = (max(4, (xs.max() - xs.min() + 1) * step * 0.5), max(4, (ys.max() - ys.min() + 1) * step * 0.5))
    return labels, centers, spans


def _ink_volumes(api, name, mask, offset=(930, 0), mode="flower", branch_surfaces=None):
    """Build thin closed petals and tube-supported bark with source contours.

    Flower depth is continuous across neighboring contours. Connected flowers
    are never cut into arbitrary labels that pull apart when the camera moves.
    """
    step = 2
    mask = mask[::step, ::step]
    rows, columns = mask.shape
    bark_depths = _branch_depth_field(branch_surfaces, mask.shape, offset, step) if mode == "bark" and branch_surfaces else None
    flower = mode in ("flower", "fallen")
    spacing = 19 if mode == "fallen" else 25 if flower else 39
    labels, centers, spans = (_flower_contours if mode == "flower" else _connected_contours)(mask, offset, step)
    vertices = []
    faces = []
    back_faces = []
    for label in np.unique(labels[mask]):
        occupied = mask & (labels == label)
        ys, xs = np.where(occupied)
        if not len(xs):
            continue
        contour_top, contour_left = int(ys.min()), int(xs.min())
        contour_depth = _contour_distance(occupied[contour_top:int(ys.max()) + 1, contour_left:int(xs.max()) + 1]) if flower else None
        center_x, center_y, variation = centers[int(label)]
        if mode == "fallen":
            depth = 90 - (center_y - 654) * (145 / 45) - 2
            thickness = 1.5
            curvature = 0.8
        elif mode == "flower":
            depth = 0
            thickness = 1.5 + 0.75 * (variation + 1)
            curvature = 1.2
        else:
            depth = 37
            thickness = 40
            curvature = 0
        grid_vertices = {}

        def vertex(column, row, back=False, cell=None):
            # Diagonal ink islands may touch in the drawing, but must not
            # share a four-face vertical edge in the solid flower geometry.
            northwest = occupied_at(column - 1, row - 1)
            northeast = occupied_at(column, row - 1)
            southeast = occupied_at(column, row)
            southwest = occupied_at(column - 1, row)
            split = 0
            if northwest and southeast and not northeast and not southwest:
                split = int(cell == (column, row))
            elif northeast and southwest and not northwest and not southeast:
                split = int(cell == (column - 1, row))
            key = (column, row, back, split)
            if key not in grid_vertices:
                u = offset[0] + column * step - 0.5
                v = offset[1] + row * step - 0.5
                if flower:
                    quadrants = ((source_at(column - 1, row - 1), -1, -1), (source_at(column, row - 1), 1, -1), (source_at(column, row), 1, 1), (source_at(column - 1, row), -1, 1))
                    occupied_count = sum(int(state) for state, _, _ in quadrants)
                    if occupied_count in (1, 3):
                        direction = 1 if occupied_count == 1 else -1
                        u += direction * 0.35 * sum(dx for state, dx, _ in quadrants if state)
                        v += direction * 0.35 * sum(dy for state, _, dy in quadrants if state)
                    elif occupied_count == 2 and ((quadrants[0][0] and quadrants[2][0]) or (quadrants[1][0] and quadrants[3][0])):
                        u += 0.35 * (1 if cell[0] == column else -1)
                        v += 0.35 * (1 if cell[1] == row else -1)
                radial = ((u - center_x) ** 2 + (v - center_y) ** 2) / spacing**2
                if flower:
                    radius_x, radius_y = spans[int(label)]
                    radial = ((u - center_x) / radius_x) ** 2 + ((v - center_y) / radius_y) ** 2
                d = depth + curvature * min(radial, 1.8)
                if mode == "flower":
                    canopy_radius = ((u - 1285) / 355) ** 2 + ((v - 240) / 390) ** 2
                    # Adjacent petal edges share one continuous depth exactly;
                    # only their interiors cup toward the viewer.
                    depths = []
                    for cx, cy in ((column - 1, row - 1), (column, row - 1), (column, row), (column - 1, row)):
                        ly, lx = cy - contour_top, cx - contour_left
                        depths.append(float(contour_depth[ly, lx]) if 0 <= ly < contour_depth.shape[0] and 0 <= lx < contour_depth.shape[1] else 0)
                    cup = min(min(depths) / 3, 1) * (curvature + 0.35 * variation)
                    d = -27 + 26 * canopy_radius - cup
                    d += 2 * math.sin(u / 90) * math.sin(v / 100)
                    d += 0.65 * math.sin(u / 11) * math.sin(v / 13)
                if mode == "fallen":
                    d -= (v - center_y) * (145 / 45)
                if back:
                    d += thickness
                if bark_depths is not None:
                    d = float(bark_depths[int(back)][row, column])
                grid_vertices[key] = len(vertices)
                vertices.append((u, v, d))
            return grid_vertices[key]

        def occupied_at(column, row):
            return (
                0 <= column < columns
                and 0 <= row < rows
                and occupied[row, column]
            )

        def source_at(column, row):
            return 0 <= column < columns and 0 <= row < rows and mask[row, column]

        for row, column in zip(ys.tolist(), xs.tolist()):
            corners = ((column, row), (column + 1, row), (column + 1, row + 1), (column, row + 1))
            front = [vertex(*corner, cell=(column, row)) for corner in corners]
            back = [vertex(*corner, back=True, cell=(column, row)) for corner in corners]
            faces.append(tuple(reversed(front)))
            back_faces.append(len(faces))
            faces.append(tuple(back))
            for side, (nx, ny) in enumerate(
                ((column, row - 1), (column + 1, row), (column, row + 1), (column - 1, row))
            ):
                if not occupied_at(nx, ny):
                    following = (side + 1) % 4
                    back_faces.append(len(faces))
                    faces.append((front[side], front[following], back[following], back[side]))
    if faces:
        obj = api.mesh(name, vertices, faces, material="source")
        obj["sourceFill"] = "pink" if flower else "bark"
        _material_faces(api, obj, "pink" if flower else "bark", back_faces)


def _blossom_cards(api, name, mask, offset=(930, 0)):
    """One flat card per printed flower, owning exactly its own pixels.

    Cards keep the painting's silhouettes crisp at full resolution and cost
    four vertices each. The label map lets the bake cut each card's alpha to
    its own contour, so neighbouring flowers never duplicate on it.
    """
    import json
    step = 2
    labels_half, centers, _ = _flower_contours(mask[::step, ::step], offset, step)
    labels = np.repeat(np.repeat(labels_half, step, axis=0), step, axis=1)[:mask.shape[0], :mask.shape[1]]
    labels = np.where(mask, labels, -1).astype(np.int32)
    full = np.full((HEIGHT, WIDTH), -1, dtype=np.int32)
    full[offset[1]:offset[1] + labels.shape[0], offset[0]:offset[0] + labels.shape[1]] = labels
    np.save(api.root / "assets/studio/world-canopy-labels.npy", full)
    vertices, faces, groups = [], [], {}
    for label in np.unique(labels[labels >= 0]):
        ys, xs = np.where(labels == label)
        u0, u1 = offset[0] + xs.min() - 1.5, offset[0] + xs.max() + 2.5
        v0, v1 = offset[1] + ys.min() - 1.5, offset[1] + ys.max() + 2.5
        cx, cy = (u0 + u1) / 2, (v0 + v1) / 2
        canopy_radius = ((cx - 1285) / 355) ** 2 + ((cy - 240) / 390) ** 2
        depth = -27 + 26 * canopy_radius + 2 * math.sin(cx / 90) * math.sin(cy / 100)
        base = len(vertices)
        vertices += [(u0, v0, depth), (u1, v0, depth), (u1, v1, depth), (u0, v1, depth)]
        groups[f"card{int(label)}"] = {"faces": [len(faces)], "fill": "pink", "card": int(label)}
        faces.append((base, base + 3, base + 2, base + 1))
    obj = api.mesh(name, vertices, faces, material="source")
    obj["sourceFill"] = "pink"
    obj["paintMode"] = "cards"
    obj["surfaceGroups"] = json.dumps(groups)
    obj["blossomCards"] = len(faces)
    return obj


def _planter(api):
    segments = 96
    # Profile rings describe the original asymmetric blue ceramic bowl, its
    # curved bottom, thick lip and inner wall rather than a flat front cutout.
    rings = [
        (1308, 781, 144, 40, 137),
        (1309, 780, 156, 46, 149),
        (1310, 670, 167, 54, 160),
        (1310, 646, 170, 55, 163),
        (1310, 644, 168, 52, 161),
        (1310, 644, 154, 45, 146),
        (1310, 655, 152, 45, 145),
        (1309, 767, 139, 39, 132),
    ]
    vertices = []
    for cx, cy, rx, ry, depth_radius in rings:
        for index in range(segments):
            angle = index / segments * math.tau
            vertices.append((cx + rx * math.cos(angle), cy + ry * math.sin(angle), 90 - depth_radius * math.sin(angle)))
    faces = []
    backs = []
    for ring in range(len(rings) - 1):
        for index in range(segments):
            following = (index + 1) % segments
            faces.append((ring * segments + index, (ring + 1) * segments + index, (ring + 1) * segments + following, ring * segments + following))
            angle = (index + 0.5) / segments * math.tau
            if math.sin(angle) < 0 and ring < 2:
                backs.append(len(faces) - 1)
    faces.append(tuple(range(segments)))
    backs.append(len(faces) - 1)
    faces.append(tuple((len(rings) - 1) * segments + index for index in range(segments - 1, -1, -1)))
    backs.append(len(faces) - 1)
    obj = api.mesh("Bonsai • thick glazed ceramic planter", vertices, faces, material="source")
    _material_faces(api, obj, "blue", backs)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    # Soil fills the vessel with a closed volume, overlapping its inner wall
    # at the top instead of leaving a visible crack around an open disk.
    soil = [(1310, 654, 92)]
    for index in range(segments):
        angle = index / segments * math.tau
        soil.append((1310 + 153 * math.cos(angle), 654 + 45.5 * math.sin(angle), 92 - 147 * math.sin(angle)))
    soil.append((1309, 764, 92))
    for index in range(segments):
        angle = index / segments * math.tau
        soil.append((1309 + 137 * math.cos(angle), 764 + 38 * math.sin(angle), 92 - 130 * math.sin(angle)))
    soil_faces = [(0, (index + 1) % segments + 1, index + 1) for index in range(segments)]
    soil_faces += [(segments + 1, segments + 2 + index, segments + 2 + (index + 1) % segments) for index in range(segments)]
    soil_faces += [(index + 1, (index + 1) % segments + 1, (index + 1) % segments + segments + 2, index + segments + 2) for index in range(segments)]
    soil_object = api.mesh("Bonsai • petal-covered soil surface", soil, soil_faces, material="source")
    soil_object["sourceFill"] = "bark"
    _material_faces(api, soil_object, "bark", range(segments, len(soil_faces)))
    # The round inlaid fitting has a raised cream lip and recessed blue center.
    # Its centerline follows the ceramic cylinder so every part contacts it.
    loop_segments, cross_segments = 48, 10
    points = []
    for index in range(loop_segments):
        angle = index * math.tau / loop_segments
        u, v = 1180 + 13 * math.cos(angle), 707 + 20 * math.sin(angle)
        depth = 90 - 160 * math.sqrt(max(0, 1 - ((u - 1310) / 167) ** 2)) - 1.3
        points.append(np.array((u, v, depth)))
    vertices, faces = [], []
    for index, center in enumerate(points):
        tangent = points[(index + 1) % loop_segments] - points[index - 1]
        tangent /= np.linalg.norm(tangent)
        normal = np.array((-tangent[1], tangent[0], 0))
        normal /= np.linalg.norm(normal)
        binormal = np.cross(tangent, normal)
        for side in range(cross_segments):
            angle = side * math.tau / cross_segments
            vertices.append(tuple(center + 2.2 * (normal * math.cos(angle) + binormal * math.sin(angle))))
            following = (index + 1) % loop_segments
            faces.append((index * cross_segments + side, index * cross_segments + (side + 1) % cross_segments, following * cross_segments + (side + 1) % cross_segments, following * cross_segments + side))
    inlay = api.mesh("Bonsai • planter round inlay", vertices, faces, material="source")
    inlay["sourceFill"] = "cream"
    for polygon in inlay.data.polygons:
        polygon.use_smooth = True


def _branches(api, ownership):
    surfaces = []
    branch_specs = [
        ([(1297, 658, 50), (1272, 621, 60), (1274, 576, 66), (1283, 540, 57), (1267, 502, 62), (1280, 463, 53), (1283, 416, 55), (1301, 376, 54)], [34, 41, 36, 31, 29, 26, 23, 18]),
        ([(1345, 660, 64), (1354, 623, 76), (1332, 584, 85), (1347, 550, 70), (1351, 503, 65), (1330, 469, 66), (1340, 429, 55), (1328, 385, 56)], [30, 27, 31, 25, 23, 23, 18, 13]),
        ([(1315, 657, 35), (1327, 615, 44), (1303, 579, 42), (1307, 538, 42), (1318, 499, 38), (1306, 461, 38), (1319, 416, 48), (1301, 379, 50)], [22, 24, 25, 23, 22, 20, 17, 12]),
        ([(1286, 481, 55), (1256, 459, 55), (1228, 437, 58), (1200, 425, 62), (1170, 418, 63), (1137, 406, 65), (1108, 409, 72)], [26, 22, 18, 16, 12, 6, 3]),
        ([(1283, 449, 63), (1262, 401, 55), (1279, 365, 59), (1280, 322, 63), (1264, 275, 70), (1287, 232, 71), (1289, 187, 67), (1306, 145, 66)], [18, 17, 15, 12, 11, 8, 6, 4]),
        ([(1332, 423, 66), (1366, 388, 70), (1385, 357, 72), (1416, 329, 77), (1450, 316, 78), (1480, 279, 82)], [18, 15, 13, 10, 7, 4]),
        ([(1281, 365, 61), (1239, 346, 68), (1207, 319, 69), (1188, 284, 74), (1166, 260, 78), (1129, 230, 79)], [13, 11, 9, 7, 5, 3]),
        ([(1281, 286, 72), (1322, 254, 79), (1348, 216, 80), (1376, 177, 81), (1402, 143, 82), (1421, 99, 86)], [10, 9, 7, 6, 4, 2]),
        ([(1268, 272, 72), (1229, 245, 80), (1208, 210, 82), (1185, 179, 86), (1167, 136, 86), (1128, 106, 92)], [9, 8, 7, 5, 3, 2]),
        ([(1291, 190, 74), (1272, 142, 86), (1297, 103, 87), (1299, 60, 88), (1299, 11, 91)], [7, 6, 5, 3, 2]),
        ([(1368, 387, 74), (1406, 415, 80), (1451, 426, 84), (1485, 410, 87), (1512, 387, 87)], [11, 9, 7, 5, 2]),
        ([(1240, 348, 72), (1202, 370, 81), (1165, 363, 86), (1139, 341, 86), (1106, 324, 90)], [9, 7, 5, 4, 2]),
        ([(1195, 447, 73), (1155, 450, 80), (1114, 432, 84), (1084, 413, 89), (1051, 413, 92)], [10, 8, 6, 4, 2]),
        ([(1168, 263, 84), (1125, 274, 88), (1084, 260, 90), (1057, 229, 96), (1025, 208, 98)], [6, 5, 4, 3, 2]),
        ([(1376, 177, 85), (1420, 195, 94), (1464, 182, 94), (1490, 153, 99)], [5, 4, 3, 2]),
        ([(1334, 519, 40), (1351, 473, 38), (1363, 440, 40), (1361, 410, 43), (1364, 374, 48), (1356, 345, 50), (1357, 312, 54), (1374, 279, 59), (1390, 249, 64)], [26, 25, 23, 24, 22, 20, 18, 15, 11]),
        ([(1301, 392, 50), (1294, 364, 55), (1285, 337, 62), (1260, 315, 66)], [19, 18, 14, 10]),
        ([(1202, 425, 62), (1192, 407, 66), (1198, 386, 70), (1194, 368, 77)], [10, 8, 6, 3]),
        ([(1138, 407, 65), (1120, 408, 69), (1090, 414, 77), (1065, 419, 85)], [7, 6, 4, 2]),
    ]
    for index, (points, radii) in enumerate(branch_specs):
        if index == 7:
            # This upper fork was only tangent to its parent after silhouette
            # fitting. Start inside the parent's actual centerline volume.
            parent_points, parent_radii, _, _ = surfaces[4]
            attachment = int(np.argmin(np.linalg.norm(parent_points - np.asarray(points[0]), axis=1)))
            points = [tuple(parent_points[attachment]), *points]
            radii = [min(radii[0] + 1, float(parent_radii[attachment])), *radii]
        surfaces.append(_tapered_branch(api, f"Bonsai • twisting branch {index + 1:02}", points, radii, material="source", ownership=ownership, stable_sections=index in (0, 1)))
    # Exposed roots curl around the trunk and sink into the petal-covered earth.
    roots = [
        ([(1290, 640, 48), (1259, 642, 22), (1224, 652, 3), (1197, 649, 5)], [17, 13, 8, 3]),
        ([(1306, 650, 38), (1290, 667, -3), (1270, 671, -23), (1252, 670, -28)], [16, 12, 7, 3]),
        ([(1332, 646, 40), (1354, 665, 5), (1383, 658, 6), (1408, 646, 30)], [15, 12, 7, 3]),
        ([(1348, 639, 70), (1380, 626, 86), (1414, 626, 100), (1434, 635, 100)], [14, 10, 6, 2]),
    ]
    root_ownership = ownership.copy()
    yy, xx = np.indices(root_ownership.shape)
    root_ownership |= ((xx - 1310) / 153) ** 2 + ((yy - 652) / 43) ** 2 < 1
    for index, (points, radii) in enumerate(roots):
        embedded = []
        soil_slope = 45.5 / 147
        for point_index, ((u, v, depth), radius) in enumerate(zip(points, radii)):
            soil_depth = 92 - (v - 654) / soil_slope
            contact_depth = soil_depth - radius * 0.45 * math.sqrt(1 + soil_slope**2) / soil_slope
            weight = min(1, point_index * 0.7)
            embedded.append((u, v, depth * (1 - weight) + contact_depth * weight))
        surfaces.append(_tapered_branch(api, f"Bonsai • spreading root {index + 1}", embedded, radii, material="source", ownership=root_ownership, stable_sections=index == 2))
    return surfaces


def _fallen_petals(api):
    # Individually cupped petals rest on the soil; source projection preserves
    # the pink fragments while thickness becomes visible away from home view.
    mask = np.zeros((1024, 1536), dtype=bool)
    pixels = api.pixels.astype(np.float32)
    red, green, blue = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    pink = (red > 140) & (red > green * 1.17) & (red > blue * 1.1)
    pink &= blue > green - (red - green) * 0.4
    yy, xx = np.indices(mask.shape)
    soil_region = ((xx - 1310) / 158) ** 2 + ((yy - 650) / 42) ** 2 < 1
    mask = pink & soil_region
    _ink_volumes(api, "Bonsai • individual fallen petals", mask[601:694, 1145:1480], offset=(1145, 601), mode="fallen")


def build_tree(api):
    _planter(api)
    flowers, bark = _flower_and_bark_masks(api.pixels)
    ownership = np.zeros(api.pixels.shape[:2], dtype=bool)
    ownership[:675, 930:1536] = flowers | bark
    # Bark printing is carried by the closed wood itself. Separate projected
    # ink skins made fringes and disconnected plates at oblique viewpoints.
    _branches(api, _close_silhouette(ownership))
    _blossom_cards(api, "Bonsai • curved blossom clusters", flowers)
    _fallen_petals(api)
