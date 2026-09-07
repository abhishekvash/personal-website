"""Bake geometry-based furniture contact shading into the clean room floors.

Run after build_world.py and prepare_room_paint(), before bake_world.py. The
editable scene is opened read-only: no mesh, material, or camera changes are
saved. Pixel processing uses Blender's image API and NumPy, without Pillow.
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TEXTURES = ROOT / "public/scene/textures"
WORK = ROOT / "assets/studio/floor-ao"
WIDTH, HEIGHT = 1536, 1024


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_pixels(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    if tuple(image.size) != (WIDTH, HEIGHT):
        raise ValueError(f"Unexpected image dimensions for {path.name}: {tuple(image.size)}")
    pixels = np.empty(WIDTH * HEIGHT * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return pixels.reshape(HEIGHT, WIDTH, 4)


def _write_pixels(path, pixels):
    height, width = pixels.shape[:2]
    image = bpy.data.images.new(path.stem, width=width, height=height, alpha=True, float_buffer=False)
    image.colorspace_settings.name = "sRGB"
    image.pixels.foreach_set(np.ascontiguousarray(pixels, dtype=np.float32).ravel())
    image.file_format = "PNG"
    image.filepath_raw = str(path)
    image.save()
    bpy.data.images.remove(image)


def _receiver(room):
    x0, x1 = room["x"]
    y0, y1 = room["y"]
    z = room["floorZ"] + .1
    mesh = bpy.data.meshes.new("ContactReceiver")
    mesh.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new("ContactReceiver", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _material(distance):
    material = bpy.data.materials.new("PhysicalFloorContact")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    occlusion = nodes.new("ShaderNodeAmbientOcclusion")
    occlusion.inputs["Color"].default_value = (1, 1, 1, 1)
    occlusion.inputs["Distance"].default_value = distance
    occlusion.samples = 16
    occlusion.only_local = False
    emission = nodes.new("ShaderNodeEmission")
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(occlusion.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
    return material


def _configure_scene(samples):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.seed = 4317
    scene.cycles.use_animated_seed = False
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "16"
    # Raw stores linear occlusion in the diagnostic PNG; no display gamma or
    # exposure can alter the value used to darken the original source colors.
    scene.view_settings.view_transform = "Raw"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    for obj in scene.objects:
        obj.visible_camera = False
        if obj.name.startswith(("Steam", "FallingPetal", "ScreenGlow")):
            obj.hide_render = True
    camera_data = bpy.data.cameras.new("FloorContactCamera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 768
    camera_data.clip_start = .1
    camera_data.clip_end = 2000
    camera = bpy.data.objects.new("FloorContactCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.rotation_euler = (0, 0, 0)
    scene.camera = camera
    return scene, camera


def _preview(rooms):
    canvas = np.ones((HEIGHT, WIDTH, 4), dtype=np.float32)
    canvas[:, :, :3] = (.95, .92, .86)
    for index, (name, room) in enumerate(rooms.items()):
        # Source images increase v with world Y, matching authored floor UVs.
        pixels = _read_pixels(TEXTURES / f"floor-{name}.png")[::-1]
        x1 = min(WIDTH, round(100 + 2 * (room["x"][1] - room["x"][0])))
        y1 = min(HEIGHT, round(100 + 2 * (room["y"][1] - room["y"][0])))
        crop = pixels[100:y1, 100:x1]
        scale = min(744 / crop.shape[1], 488 / crop.shape[0])
        w, h = round(crop.shape[1] * scale), round(crop.shape[0] * scale)
        yy = np.minimum((np.arange(h) / scale).astype(int), crop.shape[0] - 1)
        xx = np.minimum((np.arange(w) / scale).astype(int), crop.shape[1] - 1)
        x = (index % 2) * 768 + (768 - w) // 2
        y = (index // 2) * 512 + (512 - h) // 2
        canvas[y:y + h, x:x + w] = crop[yy[:, None], xx[None, :]]
    _write_pixels(WORK / "floor-ao-preview.png", canvas[::-1])


def bake_floor_contact(distance=70, samples=8, selected=None):
    """Shade fresh floor textures, reusing pristine inputs on repeated runs."""
    bpy.ops.wm.open_mainfile(filepath=str(ROOT / "assets/studio/world-studio.blend"))
    shells = [obj for obj in bpy.context.scene.objects if obj.get("roomBounds")]
    if len(shells) != 1:
        raise ValueError("Expected one building shell with roomBounds metadata.")
    rooms = json.loads(shells[0]["roomBounds"])
    if selected:
        unknown = set(selected) - rooms.keys()
        if unknown:
            raise ValueError(f"Unknown rooms: {', '.join(sorted(unknown))}")
        rooms = {name: room for name, room in rooms.items() if name in selected}
    WORK.mkdir(parents=True, exist_ok=True)
    state_path = WORK / "inputs.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    scene, camera = _configure_scene(samples)
    material = _material(distance)
    for name, room in rooms.items():
        path = TEXTURES / f"floor-{name}.png"
        base = WORK / f"{name}-base.png"
        previous = state.get(name, {})
        current_digest = _digest(path)
        if current_digest == previous.get("output"):
            if not base.exists() or _digest(base) != previous["input"]:
                raise ValueError(f"Pristine {name} floor missing; regenerate room paint before shading.")
        else:
            shutil.copyfile(path, base)
        receiver = _receiver(room)
        receiver.data.materials.append(material)
        x0, y0 = room["x"][0], room["y"][0]
        # A width of 768 at 1536 pixels gives two pixels per world unit.
        # These offsets put world (x0, y0) at source (100, 100) after Y flip.
        camera.location = (x0 + 334, y0 + 206, room["floorZ"] + 1000)
        raw_path = WORK / f"{name}-ao-raw.png"
        scene.render.filepath = str(raw_path)
        bpy.ops.render.render(write_still=True)
        ao_pixels = _read_pixels(raw_path)
        occlusion = np.where(ao_pixels[:, :, 3] > .5, ao_pixels[:, :, 0], 1)
        occlusion = np.clip(occlusion, 0, 1)[::-1]
        pixels = _read_pixels(base)
        pixels[:, :, :3] *= (.58 + .42 * occlusion[:, :, None])
        _write_pixels(path, pixels)
        state[name] = {"input": _digest(base), "output": _digest(path),
                       "distance": distance, "samples": samples,
                       "minimumFactor": float((.58 + .42 * occlusion).min())}
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        mesh = receiver.data
        bpy.data.objects.remove(receiver, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        print(f"FLOOR CONTACT {name}: minimum factor {state[name]['minimumFactor']:.3f}", flush=True)
    _preview(rooms)
    print(f"Floor contact preview: {WORK / 'floor-ao-preview.png'}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distance", type=float, default=70)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--rooms", nargs="+")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if args.distance <= 0 or args.samples < 1:
        parser.error("Distance and sample count must be positive.")
    bake_floor_contact(args.distance, args.samples, args.rooms)
