"""Scene authoring in reference-image coordinates, with genuine depth in pixels."""

import math
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

WIDTH, HEIGHT = 1536, 1024


def point(vertex):
    u, v, depth = vertex
    return Vector((u, depth, HEIGHT - v))


def triangulate(polylines):
    triangles = tessellate_polygon(polylines)
    if not triangles or isinstance(triangles[0][0], int):
        return triangles
    lookup = {tuple(v): i for i, v in enumerate(v for line in polylines for v in line)}
    return [tuple(lookup[tuple(v)] for v in triangle) for triangle in triangles]


class Studio:
    def __init__(self, root):
        self.root = Path(root)
        self.output = self.root / "assets/studio"
        (self.output / "textures").mkdir(parents=True, exist_ok=True)
        self.image = bpy.data.images.load(str(self.output / "textures/artwork.png"))
        raw = np.empty(WIDTH * HEIGHT * 4, dtype=np.float32)
        self.image.pixels.foreach_get(raw)
        self.pixels = np.clip(raw.reshape(HEIGHT, WIDTH, 4)[::-1] * 255, 0, 255).astype(np.uint8)
        self.materials = {}
        self.collection = bpy.context.scene.collection

    def material(self, name):
        if isinstance(name, bpy.types.Material):
            return name
        if name in self.materials:
            return self.materials[name]
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        emission = nodes.new("ShaderNodeEmission")
        mat.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
        if name == "source":
            texture = nodes.new("ShaderNodeTexImage")
            texture.image = self.image
            texture.interpolation = "Linear"
            mat.node_tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
        else:
            texture_path = self.output / "textures" / f"{name}.png"
            if texture_path.exists():
                texture = nodes.new("ShaderNodeTexImage")
                texture.image = bpy.data.images.load(str(texture_path), check_existing=True)
                mat.node_tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
            else:
                colors = {"blue": (30, 81, 127), "ink": (17, 56, 89), "cream": (251, 221, 170),
                          "pink": (222, 113, 139), "gold": (213, 157, 75), "wood": (222, 164, 78),
                          "bark": (107, 114, 97), "paper": (251, 227, 190)}
                rgb = colors.get(name, colors["blue"])
                linear = tuple((c / 255 / 12.92 if c / 255 <= .04045 else ((c / 255 + .055) / 1.055) ** 2.4) for c in rgb)
                emission.inputs["Color"].default_value = (*linear, 1)
        mat["sourceArtwork"] = name == "source"
        self.materials[name] = mat
        return mat

    def mesh(self, name, vertices, faces, material="source"):
        data = bpy.data.meshes.new(name)
        data.from_pydata([point(v) for v in vertices], [], faces)
        data.update()
        source = data.attributes.new(name="SourcePosition", type="FLOAT_VECTOR", domain="POINT")
        for item, position in zip(source.data, vertices):
            item.vector = position
        obj = bpy.data.objects.new(name, data)
        self.collection.objects.link(obj)
        data.materials.append(self.material(material))
        uv = data.uv_layers.new(name="ArtworkUV")
        for loop in data.loops:
            u, v, _ = vertices[loop.vertex_index]
            uv.data[loop.index].uv = (u / WIDTH, 1 - v / HEIGHT) if material in ("source", "background", "paper-background") else (u / 110, v / 110)
        obj["sourceFill"] = "blue"
        return obj

    def polygon(self, name, polygon, depth=0, material="source", fill="blue"):
        vertices = [(u, v, depth) for u, v in polygon]
        vectors = [Vector((u, v, 0)) for u, v in polygon]
        faces = triangulate([vectors])
        obj = self.mesh(name, vertices, faces, material)
        obj["sourceFill"] = fill
        return obj

    def solid(self, name, polygon, front=0, thickness=25, recede=(-.35, -.25), material="source", side_material="blue"):
        count = len(polygon)
        vertices = [(u, v, front) for u, v in polygon]
        vertices += [(u + recede[0] * thickness, v + recede[1] * thickness, front + thickness) for u, v in polygon]
        vecs = [Vector((u, v, 0)) for u, v in polygon]
        front_faces = triangulate([vecs])
        faces = front_faces + [tuple(i + count for i in reversed(face)) for face in front_faces]
        faces += [(i, (i + 1) % count, (i + 1) % count + count, i + count) for i in range(count)]
        obj = self.mesh(name, vertices, faces, material)
        obj.data.materials.append(self.material(side_material))
        for face in obj.data.polygons[len(front_faces):]:
            face.material_index = 1
        obj["sourceFill"] = side_material
        return obj

    def tube(self, name, points, radius, material="blue", project=False):
        vertices, faces = [], []
        rings = 10
        vectors = [point(p) for p in points]
        for i, position in enumerate(vectors):
            direction = (vectors[min(i + 1, len(vectors) - 1)] - vectors[max(0, i - 1)]).normalized()
            basis = direction.cross(Vector((0, 1, 0)))
            if basis.length < .01:
                basis = direction.cross(Vector((1, 0, 0)))
            basis.normalize()
            second = direction.cross(basis).normalized()
            r = radius[i] if isinstance(radius, (list, tuple)) else radius
            for j in range(rings):
                angle = j * 2 * math.pi / rings
                v = position + r * (basis * math.cos(angle) + second * math.sin(angle))
                vertices.append((v.x, HEIGHT - v.z, v.y))
            if i:
                for j in range(rings):
                    a = (i - 1) * rings + j
                    b = (i - 1) * rings + (j + 1) % rings
                    faces.append((a, b, b + rings, a + rings))
        faces += [tuple(reversed(range(rings))), tuple(range((len(points) - 1) * rings, len(points) * rings))]
        obj = self.mesh(name, vertices, faces, "source" if project else material)
        obj["sourceFill"] = material
        return obj

    def ellipsoid(self, name, center, radii, material="source"):
        vertices, faces = [], []
        segments, rings = 32, 16
        u, v, d = center
        rx, ry, rz = radii
        for i in range(rings + 1):
            phi = math.pi * i / rings
            for j in range(segments):
                theta = 2 * math.pi * j / segments
                vertices.append((u + rx * math.sin(phi) * math.cos(theta), v + ry * math.cos(phi), d + rz * math.sin(phi) * math.sin(theta)))
        for i in range(rings):
            for j in range(segments):
                a = i * segments + j
                b = i * segments + (j + 1) % segments
                faces.append((a, b, b + segments, a + segments))
        return self.mesh(name, vertices, faces, material)

    def ellipse(self, name, center, radii, depth=0, thickness=5, material="source", fill="blue", segments=64):
        u, v = center
        rx, ry = radii
        polygon = [(u + rx * math.cos(i * math.tau / segments), v + ry * math.sin(i * math.tau / segments)) for i in range(segments)]
        return self.solid(name, polygon, depth, thickness, (0, 0), material, fill)

    def ring(self, name, outer, inner, front=0, thickness=20, fill="cream"):
        n = len(outer)
        assert len(inner) == n
        vertices = [(u, v, front) for u, v in outer + inner]
        vertices += [(u - .3 * thickness, v - .22 * thickness, front + thickness) for u, v in outer + inner]
        faces = [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
        faces += [(i, i + 2 * n, (i + 1) % n + 2 * n, (i + 1) % n) for i in range(n)]
        faces += [(i + n, (i + 1) % n + n, (i + 1) % n + 3 * n, i + 3 * n) for i in range(n)]
        faces += [(i + 2 * n, i + 3 * n, (i + 1) % n + 3 * n, (i + 1) % n + 2 * n) for i in range(n)]
        obj = self.mesh(name, vertices, faces)
        obj.data.materials.append(self.material(fill))
        for face in obj.data.polygons[n:]:
            face.material_index = 1
        obj["sourceFill"] = fill
        return obj


def rounded_quad(corners, radius=15, steps=7):
    """Round a quadrilateral in image space without regularizing its drawing."""
    result = []
    for i, current in enumerate(corners):
        previous, following = Vector(corners[i - 1]), Vector(corners[(i + 1) % len(corners)])
        cur = Vector(current)
        first = cur + (previous - cur).normalized() * radius
        last = cur + (following - cur).normalized() * radius
        for j in range(steps):
            t = j / (steps - 1)
            p = first * (1 - t) ** 2 + cur * (2 * t * (1 - t)) + last * t ** 2
            result.append((p.x, p.y))
    return result
