"""Capture deterministic 1536 × 1024 browser frames of the world scene for comparison.

Requires the development server (pnpm dev, port 3000) and the studio venv with
Playwright's Chromium. Frames are read from the canvas ``data-reference-capture``
attribute written by StudioScene when ``sceneCapture=on`` and motion is off.
"""

import argparse
import base64
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright

from compare import OUTPUT, POSES, SIZE


ROOT = Path(__file__).resolve().parents[2]
REVIEW_POSES = ("review-front", "review-left", "review-right", "review-rear", "review-top")
GROUPS = {
    "home": [("home", False, "world-browser-home.png"), ("home", True, "world-clay-home.png")],
    "orbit": [(pose, False, f"world-orbit-{pose}.png") for pose in POSES],
    "clay": [(pose, True, f"world-clay-{pose}.png") for pose in POSES],
    "review": [(pose, True, f"world-clay-{pose}.png") for pose in REVIEW_POSES],
}


def capture(page, base, pose, clay, path, model, timeout):
    query = f"?sceneMotion=off&sceneCapture=on&sceneModel={model}&scenePose={pose}"
    if clay:
        query += "&sceneView=clay"
    page.goto(base + query, wait_until="load")
    try:
        page.wait_for_selector("canvas[data-reference-capture]", state="attached", timeout=timeout)
    except PlaywrightTimeout:
        status = page.evaluate("document.querySelector('.studio-artwork')?.dataset.sceneStatus")
        raise RuntimeError(f"{pose}{' clay' if clay else ''}: no capture within {timeout} ms "
                           f"(scene status: {status}).")
    data_url = page.evaluate("document.querySelector('canvas[data-reference-capture]').dataset.referenceCapture")
    header, payload = data_url.split(",", 1)
    if header != "data:image/png;base64":
        raise RuntimeError(f"Unexpected capture encoding {header!r}.")
    path.write_bytes(base64.b64decode(payload))
    size = page.evaluate("(() => { const c = document.querySelector('canvas[data-reference-capture]'); return [c.width, c.height]; })()")
    if tuple(size) != SIZE:
        raise RuntimeError(f"{path.name} canvas is {size[0]} × {size[1]}; expected 1536 × 1024. "
                           "The viewport must show the full artwork at device pixel ratio 1.")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:3000/", help="Development server origin.")
    parser.add_argument("--model", default="world", choices=("world", "published"),
                        help="'world' inspects studio-world.glb; 'published' loads studio.glb.")
    parser.add_argument("--only", nargs="+", choices=tuple(GROUPS), default=tuple(GROUPS),
                        help="Capture only these groups (home orbit clay review).")
    parser.add_argument("--timeout", type=int, default=90_000, help="Per-frame timeout in ms.")
    args = parser.parse_args()
    model = "world" if args.model == "world" else "published"
    jobs = [job for group in args.only for job in GROUPS[group]]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader",
                                                   "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": SIZE[0], "height": SIZE[1]},
                                      device_scale_factor=1, reduced_motion="reduce")
        page = context.new_page()
        errors = []
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        for pose, clay, name in jobs:
            path = capture(page, args.base, pose, clay, OUTPUT / name, model, args.timeout)
            print(f"captured {path.relative_to(ROOT)}")
        browser.close()
    if errors:
        print(f"{len(errors)} console error(s) during capture:", file=sys.stderr)
        for text in errors[:10]:
            print(f"  {text}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
