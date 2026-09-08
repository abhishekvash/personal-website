"""Assemble review evidence from deterministic in-app browser world captures.

Exit status 0 means the fidelity gate in landmarks.json passed; 1 means it failed.
"""

import argparse
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

from compare import (
    BACKGROUND, GATE, LANDMARKS, OUTPUT, POSES, REGIONS, ROOT, SIZE, TEXT,
    appearance_metrics, font, landmark_report, orbit_contact_sheet,
    paired_image, read_frame,
)


STRUCTURE_POSES = ("home", "review-front", "review-left", "review-right", "review-rear", "review-top")


def optional_frame(path):
    return read_frame(path) if path.is_file() else None


def structural_sheet(frames):
    width, height, margin, gap, caption = 480, 320, 16, 12, 30
    sheet = Image.new("RGB", (3 * width + 2 * gap + 2 * margin,
                              2 * (height + caption) + gap + 2 * margin + 42), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, margin), "Solid geometry · browser clay views", font=font(24), fill=TEXT)
    for index, pose in enumerate(STRUCTURE_POSES):
        x = margin + (index % 3) * (width + gap)
        y = margin + 42 + (index // 3) * (height + caption + gap)
        label = "Reference camera" if pose == "home" else pose.removeprefix("review-").title()
        draw.text((x, y), label, font=font(20), fill=TEXT)
        frame = frames.get(pose)
        if frame is None:
            draw.rectangle((x, y + caption, x + width - 1, y + caption + height - 1), fill="#e3dfd7")
            draw.text((x + 16, y + caption + 16), "Capture unavailable", fill=TEXT, font=font(18))
        else:
            sheet.paste(frame.resize((width, height), Image.Resampling.LANCZOS), (x, y + caption))
    return sheet


def evaluate_gate(report):
    failures = []
    flagged = report["landmark_alignment"]["flagged_names"]
    if flagged:
        failures.append(f"{len(flagged)} landmark(s) flagged: {', '.join(flagged)}")
    if report["global"]["mae_0_255"] > GATE["global_mae"]:
        failures.append(f"global MAE {report['global']['mae_0_255']:.3f} > {GATE['global_mae']}")
    for name, region in report["regions"].items():
        limit = GATE["region_mae_overrides"].get(name, GATE["region_mae"])
        if region["mae_0_255"] > limit:
            failures.append(f"{name} MAE {region['mae_0_255']:.3f} > {limit}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search", type=int, default=8,
                        help="Landmark search radius in pixels (diagnostic; the pass rule stays at the gate).")
    args = parser.parse_args()

    original = read_frame(ROOT / "landing page.png")
    browser = read_frame(OUTPUT / "world-browser-home.png")
    artwork = {pose: frame for pose in POSES
               if (frame := optional_frame(OUTPUT / f"world-orbit-{pose}.png")) is not None}
    clay = {pose: frame for pose in POSES
            if (frame := optional_frame(OUTPUT / f"world-clay-{pose}.png")) is not None}
    structure = {pose: frame for pose in STRUCTURE_POSES
                 if (frame := optional_frame(OUTPUT / f"world-clay-{pose}.png")) is not None}

    paired_image(original, browser).save(OUTPUT / "world-comparison.png", optimize=True)
    Image.blend(original, browser, .5).save(OUTPUT / "world-overlay.png", optimize=True)
    difference = np.abs(np.asarray(original, dtype=np.int16) - np.asarray(browser, dtype=np.int16))
    Image.fromarray(np.clip(difference * 4, 0, 255).astype(np.uint8)).save(
        OUTPUT / "world-difference.png", optimize=True)
    if artwork:
        orbit_contact_sheet(artwork).save(OUTPUT / "world-orbit-contact-sheet.png", optimize=True)
    if clay:
        orbit_contact_sheet(clay).save(OUTPUT / "world-clay-orbit-sheet.png", optimize=True)
    if structure:
        structural_sheet(structure).save(OUTPUT / "world-structure-sheet.png", optimize=True)

    crops = OUTPUT / "world-comparison-crops"
    crops.mkdir(exist_ok=True)
    regions = {}
    for name, (label, bounds) in REGIONS.items():
        first, second = original.crop(bounds), browser.crop(bounds)
        paired_image(first, second, f"{label} · 2×", scale=2).save(crops / f"{name}.png", optimize=True)
        regions[name] = {"bounds_xyxy": list(bounds), **appearance_metrics(first, second)}

    report = {
        "source": "landing page.png",
        "browser_capture": "assets/studio/world-browser-home.png",
        "frame_size": list(SIZE),
        "global": appearance_metrics(original, browser),
        "regions": regions,
        "orbit_captures_present": sorted(artwork),
        "orbit_captures_missing": [pose for pose in POSES if pose not in artwork],
        "landmark_alignment": landmark_report(original, browser, search=args.search),
        "gate": GATE,
    }
    failures = evaluate_gate(report)
    report["four_pixel_target_passed"] = not failures
    report["gate_failures"] = failures
    report["limitations"] = [
        f"Local patch matching searches {args.search} pixels in each direction; larger departures saturate at that radius.",
        "Color similarity does not prove connected geometry, image alignment, or faithful perspective.",
        "Full cardinal views use automatic framing and are development inspection views, outside the supported orbit.",
    ]
    (OUTPUT / "world-comparison-metrics.json").write_text(json.dumps(report, indent=2) + "\n")

    print(f"Saved world comparison, overlay, difference, {len(regions)} paired crops, "
          f"{len(artwork)}/{len(POSES)} orbit frames, {len(structure)}/{len(STRUCTURE_POSES)} structure frames.")
    print(f"Global MAE: {report['global']['mae_0_255']:.3f} / 255 (gate {GATE['global_mae']}).")
    for name, region in regions.items():
        limit = GATE["region_mae_overrides"].get(name, GATE["region_mae"])
        print(f"  {name:<12} MAE {region['mae_0_255']:6.3f} (gate {limit})")
    alignment = report["landmark_alignment"]
    print(f"Flagged landmarks: {len(alignment['flagged_names'])} / {len(LANDMARKS)}.")
    for landmark in alignment["landmarks"]:
        marker = "!!" if landmark["flagged"] else "  "
        print(f" {marker} {landmark['name']:<15} shift {landmark['displacement_px']:5.2f}px "
              f"({landmark['best_translation_xy'][0]:+d},{landmark['best_translation_xy'][1]:+d})  "
              f"patch MAE {landmark['best_patch_mae_0_255']:6.2f}")
    if failures:
        print("Fidelity gate: FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("Fidelity gate: passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
