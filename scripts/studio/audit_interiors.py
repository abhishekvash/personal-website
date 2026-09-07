"""Blender authoring diagnostics for closed volumes and furniture contacts."""

import argparse
import json
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from common import Studio
from interiors import build_interiors


def contacts(objects):
    pairs = []
    for room in ("Gaming", "Recording", "Workspace"):
        prefix = f"Interior_{room}_"
        pairs.extend((prefix + a, prefix + b) for a, b in (
            ("ChairBack", "ChairSeat"),
            ("Chair_GasLift", "Chair_Hub"),
        ))
        if room == "Recording":
            pairs.extend((prefix + a, prefix + b) for a, b in
                         (("ChairSeat", "Chair_Mechanism"), ("Chair_Mechanism", "Chair_GasLift")))
        else:
            pairs.append((prefix + "ChairSeat", prefix + "Chair_GasLift"))
        for index in range(5):
            pairs.extend((prefix + a, prefix + b) for a, b in (
                ("Chair_Hub", f"Chair_Spoke_{index}"),
                (f"Chair_Spoke_{index}", f"Chair_Caster_{index}"),
            ))
    for prefix, count, desk in (("Interior_Gaming", 2, "DeskTop"),
                                ("Interior_Recording", 2, "ConsoleDesk"),
                                ("Interior_Workspace", 3, "DeskTop")):
        leg = "ConsoleLeg" if "Recording" in prefix else "DeskLeg"
        pairs.extend((f"{prefix}_{desk}", f"{prefix}_{leg}_{index}") for index in range(count))
    for prefix in ("Interior_Gaming_MainMonitor", "Interior_Recording_ConsoleMonitor",
                   "Interior_Workspace_LeftMonitor", "Interior_Workspace_RightMonitor"):
        pairs.extend((f"{prefix}_{a}", f"{prefix}_{b}") for a, b in
                     (("Housing", "Screen"), ("Housing", "Stand"), ("Stand", "Foot")))
    pairs.extend(("Interior_Kitchen_" + a, "Interior_Kitchen_" + b) for a, b in (
        ("FryingPan", "PanHandle"), ("CookingPot", "PotHandle_0"),
        ("CookingPot", "PotHandle_1"), ("CounterTop", "CabinetBody"),
        ("CabinetBody", "LeftCreamDoor"), ("CabinetBody", "RightCreamDoor"),
    ))
    for name, obj in objects.items():
        if "_Keyboard_Key_" in name:
            pairs.append((name, name.split("_Key_", 1)[0]))
        elif name.startswith(("Interior_Recording_ConsoleKnob", "Interior_Recording_Fader")):
            pairs.append((name, "Interior_Recording_MixingConsole"))
        elif name.startswith("Interior_Kitchen_ControlLamp"):
            pairs.append((name, "Interior_Kitchen_WallControls"))
        if "connectsFirst" in obj:
            pairs.extend(((name, obj["connectsFirst"]), (name, obj["connectsSecond"])))
    return pairs


def inspect_object(obj):
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    result = {
        "name": obj.name,
        "vertices": len(mesh.verts),
        "faces": len(mesh.faces),
        "nonmanifold_edges": sum(not edge.is_manifold for edge in mesh.edges),
        "boundary_edges": sum(edge.is_boundary for edge in mesh.edges),
        "zero_area_faces": sum(face.calc_area() < 1e-8 for face in mesh.faces),
        "volume_px3": round(abs(mesh.calc_volume(signed=True)), 6),
    }
    result["closed_positive_volume"] = (
        result["nonmanifold_edges"] == 0 and result["zero_area_faces"] == 0
        and result["volume_px3"] > 1e-6
    )
    mesh.free()
    return result


def inspect_contact(first, second, cache):
    def shape(obj):
        if obj.name not in cache:
            vertices = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
            faces = [list(face.vertices) for face in obj.data.polygons]
            cache[obj.name] = (vertices, BVHTree.FromPolygons(vertices, faces))
        return cache[obj.name]
    av, a = shape(first)
    bv, b = shape(second)
    overlapping = bool(a.overlap(b))
    distance = 0.0 if overlapping else min(
        [b.find_nearest(vertex)[3] for vertex in av]
        + [a.find_nearest(vertex)[3] for vertex in bv]
    )
    return {"parts": [first.name, second.name], "surface_gap_px": round(distance, 6),
            "intersecting_surfaces": overlapping}


def render_clay(path):
    material = bpy.data.materials.new("Interior audit clay")
    material.diffuse_color = (.56, .51, .43, 1)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (.56, .51, .43, 1)
    shader.inputs["Roughness"].default_value = .8
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.data.materials.clear()
            obj.data.materials.append(material)
            for polygon in obj.data.polygons:
                polygon.material_index = 0
    scene = bpy.context.scene
    camera = bpy.data.objects.new("Interior audit camera", bpy.data.cameras.new("Interior audit camera"))
    scene.collection.objects.link(camera)
    camera.location = (1020, -1900, 620)
    camera.rotation_euler = (Vector((770, 90, 410)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 750
    camera.data.clip_end = 10000
    scene.camera = camera
    for name, position, energy in (("Key", (250, -600, 1200), 1800000),
                                    ("Fill", (1300, -300, 800), 700000)):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        scene.collection.objects.link(light)
        light.location = position
        light.rotation_euler = (Vector((770, 90, 410)) - light.location).to_track_quat("-Z", "Y").to_euler()
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = 550
    scene.world.use_nodes = True
    scene.world.node_tree.nodes.get("Background").inputs["Color"].default_value = (.26, .24, .21, 1)
    scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value = .7
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--render", type=Path, help="Optional isolated clay PNG for authoring review.")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    build_interiors(Studio(ROOT))
    bpy.context.view_layer.update()
    objects = {obj.name: obj for obj in bpy.context.scene.objects if obj.type == "MESH"}
    entries = [inspect_object(obj) for obj in objects.values()]
    cache = {}
    contact_entries = [inspect_contact(objects[a], objects[b], cache)
                       for a, b in contacts(objects) if a in objects and b in objects]
    report = {
        "purpose": "Authoring measurements; no acceptance assertions or browser asset export.",
        "object_count": len(entries),
        "closed_positive_volumes": sum(entry["closed_positive_volume"] for entry in entries),
        "nonmanifold_edges": sum(entry["nonmanifold_edges"] for entry in entries),
        "zero_area_faces": sum(entry["zero_area_faces"] for entry in entries),
        "objects": entries,
        "contacts": contact_entries,
    }
    print("INTERIOR_TOPOLOGY", json.dumps({key: value for key, value in report.items()
                                          if key not in ("objects", "contacts")}))
    print("INCOMPLETE_VOLUMES", json.dumps([entry for entry in entries
                                           if not entry["closed_positive_volume"]]))
    print("DIRECT_CONTACT_GAPS", json.dumps([entry for entry in contact_entries
                                           if entry["surface_gap_px"] > .5]))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.render:
        render_clay(args.render)


if __name__ == "__main__":
    main()
