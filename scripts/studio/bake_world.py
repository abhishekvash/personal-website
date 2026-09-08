"""Bake view-owned surface paint into compact, padded texture atlases.

For every fitted view, all triangles are depth-tested; a texel belongs to a
surface only when that surface is nearest *and* was painted from that view.
Owned texels copy the reference image (feathered toward the clean material
where the surface grazes the camera); everything else receives clean tiles.
"""

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "assets/studio"
OUT = ROOT / "assets/studio/textures"
WIDTH, HEIGHT = 1536, 1024
FILLS = ("blue", "cream", "pink", "gold", "wood", "bark", "ink", "paper")


def rasterize(triangles, owner_of_view, owners, skip=None):
    """Depth-test every triangle; return the owner map for this view's surfaces."""
    depth = np.full((HEIGHT, WIDTH), np.inf, dtype=np.float32)
    visible = np.full((HEIGHT, WIDTH), -1, dtype=np.int32)
    for triangle, owner in zip(triangles, owners):
        if triangle[0, 2] >= 1e8 or (skip is not None and skip[owner]):
            continue
        x0 = max(0, int(math.floor(triangle[:, 0].min())))
        y0 = max(0, int(math.floor(triangle[:, 1].min())))
        x1 = min(WIDTH, int(math.ceil(triangle[:, 0].max())))
        y1 = min(HEIGHT, int(math.ceil(triangle[:, 1].max())))
        if x1 <= x0 or y1 <= y0:
            continue
        a, b, c = triangle
        denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(denominator) < 1e-7:
            continue
        yy, xx = np.ogrid[y0:y1, x0:x1]
        x, y = xx + .5, yy + .5
        w0 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / denominator
        w1 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / denominator
        w2 = 1 - w0 - w1
        z = w0 * a[2] + w1 * b[2] + w2 * c[2]
        update = (w0 >= -1e-5) & (w1 >= -1e-5) & (w2 >= -1e-5) & (z < depth[y0:y1, x0:x1])
        depth[y0:y1, x0:x1][update] = z[update]
        visible[y0:y1, x0:x1][update] = owner if owner_of_view[owner] else -2
    return visible, depth


def bleed(patch, mask, rounds=2):
    """Grow owned colours outward so texture filtering never samples the tile."""
    for _ in range(rounds):
        expanded = mask.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            donor = np.roll(mask, (dy, dx), (0, 1))
            if dy < 0: donor[dy:] = False
            if dy > 0: donor[:dy] = False
            if dx < 0: donor[:, dx:] = False
            if dx > 0: donor[:, :dx] = False
            take = donor & ~expanded
            patch[take] = np.roll(patch, (dy, dx), (0, 1))[take]
            expanded |= take
        mask = expanded
    return patch


def silhouette_rim(objects, visible, depth, source, samples, radius=10, colour=40):
    """Hand the painted outlines around the studio to a rim that sits at the studio's depth.

    The tabletop and paper wall lie far from the solids they surround, so any
    outline pixel they own would drift away from the building when the camera
    orbits. Those pixels move to a thin rim mesh at the nearest solid's depth.
    """
    setting = np.array([obj["object"].startswith("Setting") for obj in objects])
    donors = {int(index) for index in np.unique(visible[visible >= 0]) if setting[index]}
    owned_setting = np.isin(visible, list(donors)) if donors else np.zeros_like(visible, dtype=bool)
    solid = (visible >= 0) & ~owned_setting
    near = solid.copy()
    nearest_depth = np.where(solid, depth, np.inf).astype(np.float32)
    for _ in range(radius):
        grown = near.copy()
        grown_depth = nearest_depth.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            shifted = np.roll(near, (dy, dx), (0, 1))
            shifted_depth = np.roll(nearest_depth, (dy, dx), (0, 1))
            take = shifted & ~grown
            grown_depth[take] = shifted_depth[take]
            grown |= take
        near, nearest_depth = grown, grown_depth
    rim = owned_setting & near & ~solid
    # Keep pixels that carry ink or colour, not the setting's own plain tone.
    plain = np.zeros_like(rim)
    for index in donors:
        fill = objects[index]["fill"]
        tile_mean = samples[fill].reshape(-1, 3).mean(axis=0) if fill in samples else np.array([250, 227, 190])
        distance = np.abs(source.astype(np.int16) - tile_mean.astype(np.int16)).sum(axis=2)
        plain |= (visible == index) & (distance < colour)
    rim &= ~plain
    return rim, np.where(rim, nearest_depth - 1.5, 0).astype(np.float32), donors


def bake():
    data = np.load(WORK / "world-projection.npz")
    owners, views = data["owners"], [str(view) for view in data["views"]]
    objects = json.loads((WORK / "world-projection.json").read_text())
    object_view = np.array([obj["view"] for obj in objects])
    is_card = np.array([obj.get("card") is not None for obj in objects])
    labels_path = WORK / "world-canopy-labels.npy"
    labels = np.load(labels_path) if labels_path.is_file() else np.full((HEIGHT, WIDTH), -1, dtype=np.int32)
    visible_by_view = {}
    for view in views:
        if view == "swatch":
            continue
        owner_of_view = object_view == view
        if not owner_of_view.any():
            continue
        visible_by_view[view], depth_map = rasterize(data["tri_" + view], owner_of_view, owners, skip=is_card)
        if view == "artwork":
            artwork_depth = depth_map
            # Blossom cards own their printed pixels outright, by contour label.
            visible_by_view[view][labels >= 0] = -3
        print(f"  rasterized {view}: {int((visible_by_view[view] >= 0).sum())} owned texels", flush=True)
    source_images = {view: np.asarray(Image.open(OUT / (view + ".png")).convert("RGB")) for view in visible_by_view}
    samples = {name: np.asarray(Image.open(OUT / f"{name}.png").convert("RGB")) for name in FILLS if (OUT / f"{name}.png").is_file()}
    rim_mask, rim_depth, rim_donors = silhouette_rim(objects, visible_by_view["artwork"], artwork_depth, source_images["artwork"], samples)
    patches = []
    mapping = {}
    if rim_mask.any():
        ys, xs = np.nonzero(rim_mask)
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        patch = np.zeros((y1 - y0, x1 - x0, 3), dtype=np.uint8)
        mask = rim_mask[y0:y1, x0:x1]
        patch[mask] = source_images["artwork"][y0:y1, x0:x1][mask]
        patch = bleed(patch, mask.copy(), rounds=3)
        padded = np.pad(patch, ((3, 3), (3, 3), (0, 0)), mode="edge")
        patches.append(("WorldRim", padded, (x0, y0, x1, y1), []))
        np.savez_compressed(WORK / "world-rim.npz", mask=rim_mask, depth=rim_depth)
        print(f"  silhouette rim: {int(rim_mask.sum())} texels from {len(rim_donors)} setting surfaces", flush=True)
    for index, obj in enumerate(objects):
        view = obj["view"]
        fallback = {"fill": obj["fill"], "object": obj["object"], "faces": obj["faces"]}
        if view not in visible_by_view:
            mapping[obj["name"]] = fallback
            continue
        visible = visible_by_view[view]
        card = obj.get("card")
        own = (labels == card) if card is not None else (visible == index)
        if index in rim_donors:
            own = own & ~rim_mask
        if not own.any():
            mapping[obj["name"]] = fallback
            continue
        x0, y0, x1, y1 = obj["bounds"]
        x0, y0 = max(0, int(math.floor(x0)) - 2), max(0, int(math.floor(y0)) - 2)
        x1, y1 = min(WIDTH, int(math.ceil(x1)) + 2), min(HEIGHT, int(math.ceil(y1)) + 2)
        if x1 <= x0 or y1 <= y0:
            mapping[obj["name"]] = fallback
            continue
        sample = samples.get(obj["fill"], samples["blue"])
        yy, xx = np.indices((y1 - y0, x1 - x0))
        tile = sample[(yy + y0) % sample.shape[0], (xx + x0) % sample.shape[1]]
        patch = tile.copy()
        mask = own[y0:y1, x0:x1].copy()
        blend = float(obj.get("blend", 1.0))
        source = source_images[view][y0:y1, x0:x1]
        if blend >= .999:
            patch[mask] = source[mask]
        else:
            mixed = (source.astype(np.float32) * blend + tile.astype(np.float32) * (1 - blend))
            patch[mask] = np.clip(mixed, 0, 255).astype(np.uint8)[mask]
        patch = bleed(patch, mask)
        faces = np.unique(data["face_ids"][owners == index]).tolist()
        if card is not None:
            alpha = np.where(own[y0:y1, x0:x1], 255, 0).astype(np.uint8)
            patch = np.dstack([patch, alpha])
        padded = np.pad(patch, ((3, 3), (3, 3), (0, 0)), mode="edge")
        patches.append((obj["name"], padded, (x0, y0, x1, y1), faces))
    patches.sort(key=lambda entry: entry[1].shape[0], reverse=True)
    atlas_size = 4096
    by_name = {obj["name"]: obj for obj in objects}
    page_count = 0
    for channels, prefix, size in ((3, "", atlas_size), (4, "cutout-", 2048)):
        selected = [entry for entry in patches if entry[1].shape[2] == channels]
        if not selected:
            continue
        pages = []
        page = np.zeros((size, size, channels), dtype=np.uint8)
        x = y = row_height = 0
        for name, patch, bounds, visible_faces in selected:
            h, w = patch.shape[:2]
            if x + w > size:
                x, y, row_height = 0, y + row_height, 0
            if y + h > size:
                pages.append(page)
                page = np.zeros((size, size, channels), dtype=np.uint8)
                x = y = row_height = 0
            page[y:y + h, x:x + w] = patch
            page_key = f"{prefix}{len(pages)}" if prefix else len(pages)
            if name == "WorldRim":
                mapping[name] = {"page": page_key, "origin": [x + 3, y + 3], "bounds": bounds, "visibleFaces": [],
                                 "object": "WorldRim", "faces": [], "fill": "paper", "size": size}
            else:
                obj = by_name[name]
                mapping[name] = {"page": page_key, "origin": [x + 3, y + 3], "bounds": bounds, "visibleFaces": visible_faces,
                                 "object": obj["object"], "faces": obj["faces"], "fill": obj["fill"], "size": size}
            x += w
            row_height = max(row_height, h)
        pages.append(page)
        for index, page in enumerate(pages):
            Image.fromarray(page).save(OUT / f"world-atlas-{prefix}{index}.png", optimize=True)
        page_count += len(pages)
    pages = list(range(page_count))
    (WORK / "world-atlas.json").write_text(json.dumps({"size": atlas_size, "objects": mapping}, ensure_ascii=False) + "\n")
    visible = visible_by_view["artwork"]
    rgb = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    valid = visible >= 0
    for channel, multiplier in enumerate((71, 137, 211)):
        rgb[..., channel][valid] = (visible[valid] * multiplier + 47) % 255
    Image.fromarray(rgb).save(WORK / "world-surface-ownership.png")
    np.save(WORK / "world-visible-owners.npy", visible)
    print(f"Baked {len(patches)} visible mesh surfaces into {len(pages)} texture atlases.")


if __name__ == "__main__":
    bake()
