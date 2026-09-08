"""Assign every face its paint by projecting the world through fitted cameras.

Faces that see the reference camera take the painting itself, so the home
view reproduces it by construction. Faces that graze or face away take the
best auxiliary reference (front, left, right, rear, top); the rest keep a
clean material swatch. Blend factors feather the seam between regimes.
"""

import json

import bpy
from mathutils import Vector

from world import ALL_VIEWS, AUXILIARY_VIEWS, HOME_VIEW
from world_paint import layers


HOME_MIN = .20      # horizontal decks see the home camera at about 0.24
AUX_MIN = .20
FEATHER = .35
EXCLUDED_PREFIXES = ("Steam", "FallingPetal", "ScreenGlow")


def choose_view(normal):
    home = normal.dot(-HOME_VIEW.away)
    if home >= HOME_MIN:
        # Never dilute the painting: anything the reference camera sees is exact.
        return "artwork", 1.0
    best, best_cos = None, AUX_MIN
    for name, view in AUXILIARY_VIEWS.items():
        cosine = normal.dot(-view.away)
        if cosine > best_cos:
            best, best_cos = name, cosine
    if best:
        return best, min(1.0, (best_cos - AUX_MIN) / (FEATHER - AUX_MIN))
    return "swatch", 0.0


def double_in_frame(camera, matrix, mesh, polygon, tolerance=.002):
    for loop_index in polygon.loop_indices:
        point = matrix @ mesh.vertices[mesh.loops[loop_index].vertex_index].co
        projected = camera.project(point)
        if not (-tolerance * 1536 <= projected.x <= 1536 * (1 + tolerance)
                and -tolerance * 1024 <= projected.y <= 1024 * (1 + tolerance)):
            return False
    return True


def paint_mode(obj):
    if obj.get("paintMode"):
        return obj["paintMode"]
    name = obj.name.lower()
    if name.startswith("setting_paperbackdrop"):
        # The backdrop is the painting's paper: it exists only in the reference view.
        return "double"
    if name.startswith("bonsai") and not any(word in name for word in ("vessel", "planter", "soil", "inlay", "ceramic")):
        # Blossoms and bark are painted ink: both faces show the same pixels.
        return "double"
    return "projected"


def paint_object(obj):
    mesh = obj.data
    uv, depth = layers(obj)
    matrix = obj.matrix_world
    normal_matrix = matrix.to_3x3()
    incoming = json.loads(obj.get("surfaceGroups", "{}"))
    if not incoming:
        incoming = {"": {"faces": list(range(len(mesh.polygons))), "fill": obj.get("sourceFill", "blue")}}
    mode = paint_mode(obj)
    outgoing = {}
    for label, group in incoming.items():
        for index in group["faces"]:
            polygon = mesh.polygons[index]
            if mode == "cards":
                view, blend = "artwork", 1.0
                key = "artwork:1.0:" + label
            elif mode == "double":
                view, blend = "artwork", 1.0
                key = "artwork:1.0:" + obj.name
            else:
                normal = (normal_matrix @ polygon.normal).normalized()
                view, blend = choose_view(normal)
                key = f"{view}:{blend:.2f}:{label}"
            camera = ALL_VIEWS.get(view)
            if camera is not None and not double_in_frame(camera, matrix, mesh, polygon):
                # A face that leaves the reference frame cannot be painted from it.
                view, blend, camera = "swatch", 0.0, None
                key = f"swatch:0.00:{label}"
            for loop_index in polygon.loop_indices:
                if camera is None:
                    uv.data[loop_index].uv = (10 / 1536, 1 - 10 / 1024)
                    depth.data[loop_index].value = 999
                    continue
                point = matrix @ mesh.vertices[mesh.loops[loop_index].vertex_index].co
                projected = camera.project(point)
                uv.data[loop_index].uv = (projected.x / 1536, 1 - projected.y / 1024)
                depth.data[loop_index].value = projected.z
            entry = outgoing.setdefault(key, {"faces": [], "fill": group.get("fill", obj.get("sourceFill", "blue")),
                                              "view": view, "blend": blend})
            if "card" in group:
                entry["card"] = group["card"]
            entry["faces"].append(index)
    obj["surfaceGroups"] = json.dumps(outgoing)
    obj["paintMode"] = mode
    obj["sourceView"] = "projected"


def paint_scene():
    counts = {}
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.name.startswith(EXCLUDED_PREFIXES):
            continue
        paint_object(obj)
        for group in json.loads(obj["surfaceGroups"]).values():
            counts[group["view"]] = counts.get(group["view"], 0) + len(group["faces"])
    print("PROJECTION PAINT " + json.dumps(counts), flush=True)
