"""Read-only Blender authoring measurements for the saved studio assembly.

Run with Blender's --background --python audit.py -- --blend studio.blend.
Reports measurements and failures; never repairs, saves, or exports geometry.
"""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import bmesh
import bpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from audit_interiors import contacts, inspect_contact


def excluded_reason(obj):
    if obj.name in ("Setting • paper backdrop", "Setting_PaperBackdrop"):
        return "Intended open background surface."
    if obj.name.startswith(("Steam", "ScreenGlow", "FallingPetal")) or "motion" in obj:
        return "Intended ambient ribbon, glow, or petal surface."
    return None


def assembly_name(name):
    if name.startswith("Interior_"):
        return " / ".join(name.split("_", 2)[:2])
    return name.split(" • ", 1)[0]


def inspect_mesh(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    data = evaluated.to_mesh()
    mesh = bmesh.new()
    try:
        mesh.from_mesh(data)
        mesh.transform(obj.matrix_world)
        signed_volume = mesh.calc_volume(signed=True)
        result = {
            "name": obj.name,
            "assembly": assembly_name(obj.name),
            "vertices": len(mesh.verts),
            "faces": len(mesh.faces),
            "boundary_edges": sum(edge.is_boundary for edge in mesh.edges),
            "nonmanifold_edges": sum(not edge.is_manifold for edge in mesh.edges),
            "zero_area_faces": sum(face.calc_area() < 1e-8 for face in mesh.faces),
            "signed_volume_px3": round(signed_volume, 6),
        }
        reasons = []
        if not mesh.faces:
            reasons.append("empty_mesh")
        if result["nonmanifold_edges"]:
            reasons.append("nonmanifold_edges")
        if result["zero_area_faces"]:
            reasons.append("zero_area_faces")
        if signed_volume <= 1e-6:
            reasons.append("inward_normals" if signed_volume < -1e-6 else "zero_volume")
        result["failures"] = reasons
        return result
    finally:
        mesh.free()
        evaluated.to_mesh_clear()


def aggregate(entries):
    return {
        "objects": len(entries),
        "objects_with_failures": sum(bool(entry["failures"]) for entry in entries),
        "boundary_edges": sum(entry["boundary_edges"] for entry in entries),
        "nonmanifold_edges": sum(entry["nonmanifold_edges"] for entry in entries),
        "zero_area_faces": sum(entry["zero_area_faces"] for entry in entries),
        "signed_volume_sum_px3": round(sum(entry["signed_volume_px3"] for entry in entries), 6),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blend", type=Path, default=ROOT / "assets/studio/studio.blend")
    parser.add_argument("--output", type=Path, default=ROOT / "assets/studio/geometry-audit.json")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    source = args.blend.resolve()
    if not source.is_file():
        parser.error(f"Blender source does not exist: {source}")
    bpy.ops.wm.open_mainfile(filepath=str(source))
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    objects = {obj.name: obj for obj in sorted(bpy.context.scene.objects, key=lambda obj: obj.name)
               if obj.type == "MESH"}
    exclusions = [{"name": obj.name, "reason": excluded_reason(obj)}
                  for obj in objects.values() if excluded_reason(obj)]
    entries = [inspect_mesh(obj, depsgraph) for obj in objects.values() if not excluded_reason(obj)]
    grouped = defaultdict(list)
    for entry in entries:
        grouped[entry["assembly"]].append(entry)

    pairs = contacts(objects)
    pairs.extend((obj.name, obj["mountedTo"]) for obj in objects.values() if "mountedTo" in obj)
    pairs.extend((obj.name, obj["floorSupport"]) for obj in objects.values() if "floorSupport" in obj)
    pairs.extend((f"Interior_Kitchen_CabinetFoot_{index}", "Interior_Kitchen_CabinetBody")
                 for index in range(2))
    pairs.extend((f"Interior_Gaming_{poster}_Frame", f"Interior_Gaming_{poster}_Print")
                 for poster in ("LeftPoster", "RightPoster"))
    cache = {}
    contact_entries = []
    seen = set()
    missing_pairs = []
    excluded_pairs = []
    for first, second in pairs:
        pair = tuple(sorted((first, second)))
        if pair in seen:
            continue
        seen.add(pair)
        if first not in objects or second not in objects:
            missing_pairs.append([first, second])
            continue
        if excluded_reason(objects[first]) or excluded_reason(objects[second]):
            excluded_pairs.append({
                "parts": [first, second],
                "reason": "Ambient animation anchors are placement references, not mechanical supports.",
            })
            continue
        contact_entries.append(inspect_contact(objects[first], objects[second], cache))
    gaps = [entry for entry in contact_entries if entry["surface_gap_px"] > .5]
    report = {
        "purpose": "Saved-scene authoring diagnostic. Measurements only; no repairs or asset export.",
        "source_blend": str(source),
        "source_modified_utc": datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "units": "Scene units correspond to source-image pixels; volumes use cubic scene units.",
        "limitations": [
            "Assembly volumes are sums of component signed volumes, not Boolean union volumes.",
            "Manifold positive-volume components do not prove an assembly is connected or free of self-intersections.",
            "Support pairs are selected intended mechanical contacts, not an exhaustive assembly collision analysis.",
            "Contact gaps use triangle intersection or nearest vertex-to-surface distance; edge-edge distances and fully contained parts may need artist review.",
            "This does not measure reference-image fidelity, silhouette alignment, lighting, or browser appearance.",
        ],
        "summary": aggregate(entries),
        "assemblies": {name: aggregate(items) for name, items in sorted(grouped.items())},
        "excluded_objects": exclusions,
        "objects": entries,
        "object_failures": [entry for entry in entries if entry["failures"]],
        "support_contacts": contact_entries,
        "support_gaps_over_half_px": gaps,
        "missing_support_pairs": missing_pairs,
        "excluded_support_pairs": excluded_pairs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print("GEOMETRY_AUDIT", json.dumps(report["summary"]))
    print("ASSEMBLIES", json.dumps(report["assemblies"]))
    print("OBJECT_FAILURES", json.dumps([{key: entry[key] for key in (
        "name", "nonmanifold_edges", "zero_area_faces", "signed_volume_px3", "failures")}
        for entry in report["object_failures"]]))
    print("SUPPORT_GAPS", json.dumps(gaps))
    print(f"REPORT {args.output.resolve()}")


if __name__ == "__main__":
    main()
