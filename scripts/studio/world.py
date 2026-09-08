"""One orthographic camera and orthogonal coordinate system for the whole scene.

Every number here comes from assets/studio/world_fit.json, written by
world_fit.py from painting landmarks. World units are painting pixels at the
reference camera; X is right, Y is back (front faces negative Y), Z is up.
"""
import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

FIT_PATH = Path(__file__).resolve().parents[2] / "assets/studio/world_fit.json"
FIT = json.loads(FIT_PATH.read_text())
GEOMETRY = FIT["geometry"]

AZIMUTH = math.radians(FIT["camera"]["azimuth_degrees"])
ELEVATION = math.radians(FIT["camera"]["elevation_degrees"])
SCALE = FIT["camera"]["scale"]
ANCHOR = Vector((0, 0, 0))
IMAGE_ANCHOR = Vector((*FIT["camera"]["origin_uv"], 0))
RIGHT = Vector((math.cos(AZIMUTH), -math.sin(AZIMUTH), 0))
UP = Vector((math.sin(AZIMUTH) * math.sin(ELEVATION), math.cos(AZIMUTH) * math.sin(ELEVATION), math.cos(ELEVATION)))
AWAY = UP.cross(RIGHT)
TARGET = ANCHOR + RIGHT * (768 - IMAGE_ANCHOR.x) / SCALE + UP * (IMAGE_ANCHOR.y - 512) / SCALE


def project(position):
    p = Vector(position) - ANCHOR
    return Vector((IMAGE_ANCHOR.x + SCALE * RIGHT.dot(p), IMAGE_ANCHOR.y - SCALE * UP.dot(p), SCALE * AWAY.dot(p)))


def unproject(position):
    u, v, depth = position
    return ANCHOR + RIGHT * (u - IMAGE_ANCHOR.x) / SCALE + UP * (IMAGE_ANCHOR.y - v) / SCALE + AWAY * depth / SCALE


def legacy_to_world(obj, depth_offset=0):
    matrix = obj.matrix_world.copy()
    for vertex in obj.data.vertices:
        p = matrix @ vertex.co
        vertex.co = unproject((p.x, 1024 - p.z, p.y + depth_offset))
    obj.matrix_world = Matrix.Identity(4)
    obj["coordinateSpace"] = "world"
    obj.data.update()


def create_camera():
    data = bpy.data.cameras.new("ReferenceCamera")
    obj = bpy.data.objects.new("ReferenceCamera", data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = TARGET - AWAY * 3000
    obj.rotation_euler = (TARGET - obj.location).to_track_quat("-Z", "Y").to_euler()
    data.type = "ORTHO"
    data.ortho_scale = 1536 / SCALE
    data.clip_start = .1
    data.clip_end = 10000
    scene = bpy.context.scene
    scene.camera = obj
    scene.render.resolution_x = 1536
    scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    return obj


def metadata():
    return {"cameraTarget": [TARGET.x, TARGET.z, -TARGET.y], "horizontalLimitDegrees": 8,
            "verticalLimitDegrees": 4, "sourceSize": [1536, 1024]}


class View:
    """An auxiliary orthographic reference camera fitted to one reference image."""

    def __init__(self, name, spec):
        self.name = name
        self.image = spec["image"]
        azimuth = math.radians(spec["azimuth_degrees"])
        elevation = math.radians(spec["elevation_degrees"])
        self.scale_u = spec["scale_u"]
        self.scale_v = spec["scale_v"]
        self.origin = Vector(spec["origin_uv"])
        self.right = Vector((math.cos(azimuth), -math.sin(azimuth), 0))
        self.up = Vector((math.sin(azimuth) * math.sin(elevation), math.cos(azimuth) * math.sin(elevation), math.cos(elevation)))
        self.away = self.up.cross(self.right)

    def project(self, position):
        p = Vector(position)
        return Vector((self.origin.x + self.scale_u * self.right.dot(p),
                       self.origin.y - self.scale_v * self.up.dot(p),
                       self.away.dot(p)))


def _mirrored_view(name, spec):
    """The right side has no reference; mirror the left elevation for it."""
    mirrored = dict(spec)
    mirrored["azimuth_degrees"] = -spec["azimuth_degrees"]
    mirrored["origin_uv"] = [1535 - spec["origin_uv"][0], spec["origin_uv"][1]]
    mirrored["image"] = spec["image"]
    mirrored["mirrored"] = True
    return View(name, mirrored)


HOME_VIEW = View("artwork", {"image": "landing page.png", "azimuth_degrees": FIT["camera"]["azimuth_degrees"],
                             "elevation_degrees": FIT["camera"]["elevation_degrees"],
                             "scale_u": SCALE, "scale_v": SCALE, "origin_uv": FIT["camera"]["origin_uv"]})
AUXILIARY_VIEWS = {name: View(name, spec) for name, spec in FIT.get("views", {}).items()}
if "view-left" in AUXILIARY_VIEWS and "view-right" not in AUXILIARY_VIEWS:
    AUXILIARY_VIEWS["view-right"] = _mirrored_view("view-right", FIT["views"]["view-left"])
ALL_VIEWS = {"artwork": HOME_VIEW, **AUXILIARY_VIEWS}
