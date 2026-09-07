"""Rebuild the illustrated studio and its browser assets in dependency order."""

import argparse
import importlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def require_image_dependencies():
    missing = []
    for module, package in (("PIL", "Pillow"), ("numpy", "numpy")):
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    if missing:
        install = shlex.join([sys.executable, "-m", "pip", "install", *missing])
        raise RuntimeError(
            f"Cannot import {', '.join(missing)} with {sys.executable}. "
            "Preparation and atlas baking use this same Python interpreter. "
            f"Install its dependencies with: {install}"
        )


def resolve_blender(value):
    executable = shutil.which(os.path.expanduser(value))
    if executable is None:
        raise RuntimeError(
            f"Blender executable not found or not executable: {value!r}. "
            "Pass --blender /path/to/blender or set BLENDER."
        )
    return str(Path(executable).resolve())


def run_stage(number, description, command):
    print(f"[{number}/9] {description}", flush=True)
    try:
        subprocess.run(command, cwd=ROOT, check=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"Stage {number} failed with exit code {error.returncode}: {description}. "
            "See the tool output above. Remaining stages were not run."
        ) from error
    except OSError as error:
        raise RuntimeError(f"Could not start stage {number}: {error}") from error


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild source textures, the editable Blender scene, ownership atlases, "
            "and the final GLB. Replaces generated studio assets."
        )
    )
    parser.add_argument(
        "--blender",
        default=os.environ.get("BLENDER") or "blender",
        metavar="EXECUTABLE",
        help="Blender executable or path; defaults to BLENDER, then blender on PATH.",
    )
    parser.add_argument("--preview", action="store_true", help="Keep the rebuilt world scene in development preview until visual review.")
    args = parser.parse_args()
    try:
        require_image_dependencies()
        blender = resolve_blender(args.blender)
        if not (ROOT / "landing page.png").is_file():
            raise RuntimeError(f"Missing source artwork: {ROOT / 'landing page.png'}")

        python = sys.executable
        build = [
            blender,
            "--background",
            "--factory-startup",
            "--python-exit-code", "1",
            "--python", str(HERE / "build_world.py"),
        ]
        run_stage(1, "Prepare source artwork and material samples",
                  [python, str(HERE / "prepare.py")])
        run_stage(2, "Extend clean source room materials", [python, str(HERE / "world_room_paint.py")])
        run_stage(3, "Separate observatory artwork surfaces", [python, str(HERE / "world_prepare.py")])
        run_stage(4, "Build shared world geometry and surface ownership", build)
        contact = [blender, "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(HERE / "world_floor_ao.py")]
        run_stage(5, "Bake physical furniture contact shading", contact)
        run_stage(6, "Bake owned artwork onto surfaces", [python, str(HERE / "bake_world.py")])
        shadow = [blender, "--background", "--python-exit-code", "1", "--python", str(HERE / "world_shadows.py")]
        run_stage(7, "Cast shadows from the actual solids", shadow)
        run_stage(8, "Combine shadows with source wood grain", [python, str(HERE / "compose_world_table.py")])
        run_stage(9, "Apply atlases and export the browser scene",
                  [*build, "--", "--finalize"])
        if not args.preview:
            for original, target in (("studio-world.glb", "studio.glb"), ("scene-world.json", "scene.json")):
                shutil.copyfile(ROOT / "public/scene" / original, ROOT / "public/scene" / target)
    except RuntimeError as error:
        print(f"Studio rebuild failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Studio rebuild interrupted. Rerun the full pipeline before using its outputs.",
              file=sys.stderr)
        return 130

    print(f"Editable scene: {ROOT / 'assets/studio/world-studio.blend'}")
    print(f"Browser scene: {ROOT / 'public/scene/studio-world.glb'}")
    print("Rebuild complete. Visual fidelity still requires browser review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
