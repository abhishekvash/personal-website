"""Rebuild the illustrated studio and its browser assets in dependency order."""

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def require_image_dependencies(python):
    probe = "import PIL, numpy, scipy"
    result = subprocess.run([python, "-c", probe], capture_output=True, text=True)
    if result.returncode != 0:
        install = shlex.join(["uv", "pip", "install", "--python", python, "-r",
                              str(HERE / "requirements.txt")])
        raise RuntimeError(
            f"{python} cannot import Pillow, NumPy and SciPy. "
            "Preparation, fitting and atlas baking use this interpreter. "
            f"Create it with: uv venv .venv-studio --python 3.13 && {install}"
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
    print(f"[{number}/5] {description}", flush=True)
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
    default_python = ROOT / ".venv-studio/bin/python"
    parser.add_argument(
        "--python",
        default=str(default_python) if default_python.is_file() else sys.executable,
        metavar="EXECUTABLE",
        help="Python with Pillow, NumPy and SciPy for the image stages; defaults to .venv-studio when present.",
    )
    args = parser.parse_args()
    try:
        require_image_dependencies(args.python)
        blender = resolve_blender(args.blender)
        if not (ROOT / "landing page.png").is_file():
            raise RuntimeError(f"Missing source artwork: {ROOT / 'landing page.png'}")

        python = args.python
        build = [
            blender,
            "--background",
            "--factory-startup",
            "--python-exit-code", "1",
            "--python", str(HERE / "build_world.py"),
        ]
        run_stage(1, "Solve the reference camera and proportions from the painting",
                  [python, str(HERE / "world_fit.py"), "--write"])
        run_stage(2, "Prepare source artwork and material samples",
                  [python, str(HERE / "prepare.py")])
        run_stage(3, "Build world geometry, project paint, and export ownership", build)
        run_stage(4, "Bake owned artwork onto surfaces", [python, str(HERE / "bake_world.py")])
        run_stage(5, "Apply atlases and export the browser scene",
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
