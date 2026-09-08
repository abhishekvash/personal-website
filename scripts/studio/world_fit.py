"""Solve the reference camera and the studio's principal dimensions from the painting.

Correspondences live in landmarks.json under "fit". The result is written to
assets/studio/world_fit.json and read by world.py and the geometry builders.
Runs with the studio venv (NumPy + SciPy); never imported inside Blender.
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUT = ROOT / "assets/studio/world_fit.json"
TABLE = json.loads((HERE / "landmarks.json").read_text())["fit"]


class Camera:
    """Orthographic camera: world (x right, y back, z up) → painting pixels."""

    def __init__(self, azimuth, elevation, scale, u0, v0):
        self.azimuth, self.elevation, self.scale, self.u0, self.v0 = azimuth, elevation, scale, u0, v0
        a, e = azimuth, elevation
        self.right = np.array([math.cos(a), -math.sin(a), 0.0])
        self.up = np.array([math.sin(a) * math.sin(e), math.cos(a) * math.sin(e), math.cos(e)])
        self.away = np.cross(self.up, self.right)

    def project(self, points):
        points = np.atleast_2d(points)
        u = self.u0 + self.scale * points @ self.right
        v = self.v0 - self.scale * points @ self.up
        return np.stack([u, v], axis=1)


class Model:
    """Parameter vector layout shared by the residual and the report."""

    def __init__(self, table):
        self.names = []
        self.initial = []
        self.lower = []
        self.upper = []
        for name, (value, low, high) in table["parameters"].items():
            self.names.append(name)
            self.initial.append(value)
            self.lower.append(low)
            self.upper.append(high)
        self.index = {name: i for i, name in enumerate(self.names)}

    def unpack(self, vector):
        values = {name: float(vector[i]) for name, i in self.index.items()}
        values["__zero__"] = 0.0
        return values


def feature_point(p, spec):
    """World point of a named feature given the current parameters."""
    kind = spec[0]
    if kind == "box":
        _, box, corner = spec
        x0, x1, y0, y1, z0, z1 = (p[key] for key in TABLE["boxes"][box])
        return np.array([x1 if "R" in corner else x0,
                         y1 if "K" in corner else y0,
                         z1 if "T" in corner else z0])
    if kind == "point":
        return np.array([p[spec[1]], p[spec[2]], p[spec[3]]])
    if kind == "dome_top":
        return np.array([p["dome_x"], p["dome_y"], p["dome_shoulder_z"] + p["dome_r"]])
    raise ValueError(spec)


def residuals(vector, model, correspondences):
    p = model.unpack(vector)
    camera = Camera(p["azimuth"], p["elevation"], p["scale"], p["u0"], p["v0"])
    out = []
    for item in correspondences:
        weight = item.get("weight", 1.0)
        kind = item["feature"][0]
        if kind == "dome_extreme":
            centre = np.array([p["dome_x"], p["dome_y"], p["dome_shoulder_z"]])
            side = 1 if item["feature"][1] == "right" else -1
            point = centre + side * p["dome_r"] * camera.right
            projected = camera.project(point)[0]
        elif kind == "circle":
            _, cx, cy, cz, cr = item["feature"]
            angle = p[item["angle"]]
            centre = np.array([p[cx], p[cy], p[cz]])
            point = centre + p[cr] * (math.cos(angle) * np.array([1, 0, 0]) + math.sin(angle) * np.array([0, 1, 0]))
            projected = camera.project(point)[0]
        elif kind == "radius_v":
            # A circle in a vertical side plane appears as an ellipse whose vertical
            # semi-axis is r * scale * cos(elevation) ... approximated as r * scale.
            out.append(weight * (p[item["feature"][1]] * p["scale"] * math.cos(p["elevation"]) - item["pixels"]))
            continue
        else:
            projected = camera.project(feature_point(p, item["feature"]))[0]
        out.extend(weight * (projected - np.array(item["uv"])))
    for prior in TABLE.get("priors", []):
        # ratio priors: value_a / value_b should equal target
        a = p[prior["a"]] - p.get(prior.get("a0", "__zero__"), 0.0)
        b = p[prior["b"]] - p.get(prior.get("b0", "__zero__"), 0.0)
        out.append(prior.get("weight", 1.0) * 100 * (a / b - prior["target"]))
    for tie in TABLE.get("ties", []):
        # soft equality between two parameters, in world units
        out.append(tie.get("weight", 1.0) * (p[tie["a"]] - p[tie["b"]] - tie.get("offset", 0.0)))
    return np.array(out)


WALL = 20.0


def derive_geometry(p):
    """Turn solved parameters into the corner-frame solids the builders consume."""
    plinth_top = max(p["gz0"], 20.0)
    storeys = {
        "Ground": {"x": [p["gx0"], p["gx1"]], "y": [p["gy0"], p["gy1"]], "z": [plinth_top, p["gz1"]]},
        "Recording": {"x": [p["rx0"], p["rx1"]], "y": [p["ry0"], p["ry1"]], "z": [p["gz1"], p["rz1"]]},
        "Gaming": {"x": [p["ux0"], p["ux1"]], "y": [p["uy0"], p["uy1"]], "z": [p["rz1"], p["uz1"]]},
    }
    g, r, u = storeys["Ground"], storeys["Recording"], storeys["Gaming"]
    mid = (g["x"][0] + g["x"][1]) / 2
    rooms = {
        "Workspace": {"x": [g["x"][0] + WALL, mid - 10], "y": [g["y"][0], g["y"][1] - WALL],
                      "floorZ": g["z"][0] + WALL, "ceilingZ": g["z"][1] - WALL,
                      "openingX": [g["x"][0] + WALL, mid - 10], "frontY": g["y"][0],
                      "floorFill": "gold", "rearFill": "pink", "storey": "Ground"},
        "Kitchen": {"x": [mid + 10, g["x"][1] - WALL], "y": [g["y"][0], g["y"][1] - WALL],
                    "floorZ": g["z"][0] + WALL, "ceilingZ": g["z"][1] - WALL,
                    "openingX": [mid + 10, g["x"][1] - WALL], "frontY": g["y"][0],
                    "floorFill": "gold", "rearFill": "gold", "storey": "Ground"},
        "Recording": {"x": [r["x"][0] + WALL, r["x"][1] - WALL], "y": [r["y"][0], r["y"][1] - WALL],
                      "floorZ": r["z"][0] + WALL, "ceilingZ": r["z"][1] - WALL,
                      "openingX": [r["x"][0] + WALL, r["x"][1] - WALL - 90], "frontY": r["y"][0],
                      "floorFill": "pink", "rearFill": "pink", "storey": "Recording"},
        "Gaming": {"x": [u["x"][0] + WALL, u["x"][1] - WALL], "y": [u["y"][0], u["y"][1] - WALL],
                   "floorZ": u["z"][0] + WALL, "ceilingZ": u["z"][1] - WALL,
                   "openingX": [u["x"][0] + WALL + 100, u["x"][1] - WALL - 45], "frontY": u["y"][0],
                   "usableX": [u["x"][0] + WALL + 100, u["x"][1] - WALL],
                   "floorFill": "pink", "rearFill": "pink", "storey": "Gaming"},
    }
    ports = []
    corner = 20.0
    for storey, name in (("Gaming", "upper"), ("Recording", "middle"), ("Ground", "lower"), ("Ground", "small")):
        y, z, radius = p[f"port_{name}_y"], p[f"port_{name}_z"], p[f"port_{name}_r"]
        box = storeys[storey]
        # The bore must stay on the flat part of the side wall, clear of the fillets.
        y = min(max(y, box["y"][0] + radius + corner + 4), box["y"][1] - radius - corner - 4)
        z = min(max(z, box["z"][0] + radius + corner + 4), box["z"][1] - radius - corner - 4)
        for side, label in ((-1, "Left"), (1, "Right")):
            port_y = y
            if side > 0 and name == "lower":
                # The kitchen's right wall carries a control panel, not a window.
                port_y = box["y"][0] + (box["y"][1] - box["y"][0]) * .7
            ports.append({"name": f"{storey}{label}{'Small' if name == 'small' else ''}Porthole",
                          "storey": storey, "side": side, "y": port_y, "z": z, "r": radius})
    # Feet: unproject each painted foot base onto the plinth's front face plane.
    camera = Camera(p["azimuth"], p["elevation"], p["scale"], p["u0"], p["v0"])
    py0 = g["y"][0] - 14
    feet = []
    for fu, fv in TABLE.get("feet_uv", []):
        base = camera.up * ((p["v0"] - fv) / p["scale"]) + camera.right * ((fu - p["u0"]) / p["scale"])
        depth = (py0 - base[1]) / camera.away[1]
        point = base + camera.away * depth
        feet.append([float(point[0]), float(py0 + 24)])
    if feet:
        feet[-1][1] = g["y"][1] + 8 - 24   # the rear-left foot sits on the back edge
        feet.append([feet[3][0], g["y"][1] + 8 - 24])
    return {
        "wall": WALL,
        "feet": feet,
        "cornerRadius": 20.0,
        "storeys": storeys,
        "rooms": rooms,
        "plinth": {"x": [g["x"][0] - 8, g["x"][1] + 8], "y": [g["y"][0] - 14, g["y"][1] + 8],
                   "z": [8.0, plinth_top], "footHeight": 8.0},
        "ports": ports,
        "frontPort": {"x": p["port_front_x"], "y": r["y"][0], "z": p["port_front_z"], "r": p["port_front_r"]},
        "vent": {"x": [u["x"][0] + 18, u["x"][0] + 84], "y": u["y"][0], "z": [u["z"][0] + 80, u["z"][1] - 40]},
        "dome": {"x": p["dome_x"], "y": p["dome_y"], "shoulderZ": p["dome_shoulder_z"], "r": p["dome_r"],
                 "roofZ": u["z"][1]},
        "fittings": {"antenna": [p["antenna_x"], p["antenna_y"]], "chimney": [p["chimney_x"], p["chimney_y"]]},
        "planter": {"x": p["planter_x"], "y": p["planter_y"], "r": p["planter_r"], "rBase": p["planter_rb"], "h": p["planter_h"]},
    }


class ViewCamera(Camera):
    """Orthographic camera with independent horizontal and vertical pixel scales."""

    def __init__(self, azimuth, elevation, scale_u, scale_v, u0, v0):
        super().__init__(azimuth, elevation, 1.0, u0, v0)
        self.scale_u, self.scale_v = scale_u, scale_v

    def project(self, points):
        points = np.atleast_2d(points)
        u = self.u0 + self.scale_u * points @ self.right
        v = self.v0 - self.scale_v * points @ self.up
        return np.stack([u, v], axis=1)


def solve_views(p):
    """Fit each auxiliary reference camera with the painting geometry held fixed."""
    views = {}
    for name, spec in TABLE.get("views", {}).items():
        keys = list(spec["parameters"])
        initial = [spec["parameters"][k][0] for k in keys]
        lower = [spec["parameters"][k][1] for k in keys]
        upper = [spec["parameters"][k][2] for k in keys]

        def residual(vector):
            q = dict(zip(keys, vector))
            camera = ViewCamera(q["azimuth"], q["elevation"], q["scale_u"], q["scale_v"], q["u0"], q["v0"])
            out = []
            for item in spec["correspondences"]:
                kind = item["feature"][0]
                if kind == "dome_top":
                    point = feature_point(p, item["feature"])
                else:
                    point = feature_point(p, item["feature"])
                projected = camera.project(point)[0]
                out.extend(item.get("weight", 1.0) * (projected - np.array(item["uv"])))
            return np.array(out)

        result = least_squares(residual, np.array(initial, dtype=float), bounds=(lower, upper),
                               loss="soft_l1", f_scale=3.0)
        q = dict(zip(keys, result.x))
        errors = np.abs(residual(result.x)).reshape(-1, 2)
        distances = np.hypot(errors[:, 0], errors[:, 1])
        worst = float(distances.max())
        for item, distance in zip(spec["correspondences"], distances):
            if distance > 12:
                print(f"      {distance:6.1f}px {name} {item['feature']}")
        print(f"  {name:<11} az {math.degrees(q['azimuth']):7.2f}° el {math.degrees(q['elevation']):6.2f}° "
              f"scale ({q['scale_u']:.3f}, {q['scale_v']:.3f}) origin ({q['u0']:.0f}, {q['v0']:.0f})  worst {worst:.1f}px")
        views[name] = {"image": spec["image"], "azimuth_degrees": math.degrees(q["azimuth"]),
                       "elevation_degrees": math.degrees(q["elevation"]), "scale_u": q["scale_u"],
                       "scale_v": q["scale_v"], "origin_uv": [q["u0"], q["v0"]], "worst_px": worst}
    return views


def overlay(p, camera):
    """Draw the solved solids over the painting for visual review."""
    from PIL import Image, ImageDraw
    image = Image.open(ROOT / "landing page.png").convert("RGB")
    draw = ImageDraw.Draw(image)

    def line(a, b, colour):
        (u0, v0), (u1, v1) = camera.project([a, b])
        draw.line([(u0, v0), (u1, v1)], fill=colour, width=2)

    for box, keys in TABLE["boxes"].items():
        x0, x1, y0, y1, z0, z1 = (p[k] for k in keys)
        corners = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
        edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
        for a, b in edges:
            line(corners[a], corners[b], (255, 0, 0))
    centre = np.array([p["dome_x"], p["dome_y"], p["dome_shoulder_z"]])
    ring = [centre + p["dome_r"] * np.array([math.cos(a), math.sin(a), 0]) for a in np.linspace(0, 2 * math.pi, 64)]
    for a, b in zip(ring, ring[1:]):
        line(a, b, (0, 160, 255))
    line(centre, centre + np.array([0, 0, p["dome_r"]]), (0, 160, 255))
    for z, radius in ((0.0, p["planter_rb"]), (p["planter_h"], p["planter_r"])):
        pc = np.array([p["planter_x"], p["planter_y"], z])
        ring = [pc + radius * np.array([math.cos(a), math.sin(a), 0]) for a in np.linspace(0, 2 * math.pi, 64)]
        for a, b in zip(ring, ring[1:]):
            line(a, b, (0, 200, 0))
    for name in ("upper", "middle", "lower", "small"):
        c = np.array([p["gx0"], p[f"port_{name}_y"], p[f"port_{name}_z"]])
        ring = [c + p[f"port_{name}_r"] * np.array([0, math.cos(a), math.sin(a)]) for a in np.linspace(0, 2 * math.pi, 32)]
        for a, b in zip(ring, ring[1:]):
            line(a, b, (255, 200, 0))
    for item in TABLE["correspondences"]:
        if "uv" in item:
            u, v = item["uv"]
            draw.ellipse([u - 3, v - 3, u + 3, v + 3], outline=(255, 255, 255), width=2)
    image.save(ROOT / "assets/studio/world-fit-overlay.png", optimize=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write assets/studio/world_fit.json.")
    args = parser.parse_args()
    model = Model(TABLE)
    correspondences = TABLE["correspondences"]
    result = least_squares(residuals, np.array(model.initial, dtype=float),
                           bounds=(model.lower, model.upper),
                           args=(model, correspondences), loss="soft_l1", f_scale=3.0,
                           max_nfev=20000)
    p = model.unpack(result.x)
    camera = Camera(p["azimuth"], p["elevation"], p["scale"], p["u0"], p["v0"])
    report = []
    for item in correspondences:
        kind = item["feature"][0]
        if kind == "radius_v":
            continue
        if kind == "dome_extreme":
            centre = np.array([p["dome_x"], p["dome_y"], p["dome_shoulder_z"]])
            side = 1 if item["feature"][1] == "right" else -1
            projected = camera.project(centre + side * p["dome_r"] * camera.right)[0]
        elif kind == "circle":
            _, cx, cy, cz, cr = item["feature"]
            angle = p[item["angle"]]
            centre = np.array([p[cx], p[cy], p[cz]])
            projected = camera.project(centre + p[cr] * np.array([math.cos(angle), math.sin(angle), 0]))[0]
        else:
            projected = camera.project(feature_point(p, item["feature"]))[0]
        error = projected - np.array(item["uv"])
        report.append({"name": item["name"], "uv": item["uv"],
                       "projected": [round(float(x), 1) for x in projected],
                       "error_px": round(float(np.hypot(*error)), 2)})
    worst = sorted(report, key=lambda r: -r["error_px"])
    print(f"solved in {result.nfev} evaluations; cost {result.cost:.2f}")
    print("camera: azimuth %.2f° elevation %.2f° scale %.4f origin (%.1f, %.1f)" % (
        math.degrees(p["azimuth"]), math.degrees(p["elevation"]), p["scale"], p["u0"], p["v0"]))
    for name in model.names:
        if name in ("azimuth", "elevation", "scale", "u0", "v0") or name.startswith("angle_"):
            continue
        print(f"  {name:<22} {p[name]:9.2f}")
    errors = np.array([r["error_px"] for r in report])
    print(f"landmark error: mean {errors.mean():.2f}px  median {np.median(errors):.2f}px  max {errors.max():.2f}px")
    for r in worst[:12]:
        print(f"  {r['error_px']:6.2f}px  {r['name']:<34} painted {r['uv']} solved {r['projected']}")
    print("auxiliary views:")
    views = solve_views(p)
    if args.write:
        overlay(p, camera)
        payload = {
                   "views": views,"camera": {"azimuth_degrees": math.degrees(p["azimuth"]),
                              "elevation_degrees": math.degrees(p["elevation"]),
                              "scale": p["scale"], "origin_uv": [p["u0"], p["v0"]]},
                   "parameters": {k: v for k, v in p.items() if not k.startswith("angle_") and k != "__zero__"},
                   "geometry": derive_geometry(p),
                   "residuals": report,
                   "summary": {"mean_px": float(errors.mean()), "max_px": float(errors.max())}}
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
