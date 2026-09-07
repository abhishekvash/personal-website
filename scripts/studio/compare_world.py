"""Assemble review evidence from deterministic in-app browser world captures."""

import json

from PIL import Image, ImageDraw

from compare import (
    BACKGROUND, LANDMARKS, OUTPUT, POSES, REGIONS, ROOT, SIZE, TEXT,
    appearance_metrics, font, landmark_report, orbit_contact_sheet,
    paired_image, read_frame,
)


def structural_sheet():
    poses = ("home", "review-front", "review-left", "review-right", "review-rear", "review-top")
    width, height, margin, gap, caption = 480, 320, 16, 12, 30
    sheet = Image.new("RGB", (3 * width + 2 * gap + 2 * margin,
                              2 * (height + caption) + gap + 2 * margin + 42), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, margin), "Solid geometry · browser clay views", font=font(24), fill=TEXT)
    for index, pose in enumerate(poses):
        x = margin + (index % 3) * (width + gap)
        y = margin + 42 + (index // 3) * (height + caption + gap)
        label = "Reference camera" if pose == "home" else pose.removeprefix("review-").title()
        draw.text((x, y), label, font=font(20), fill=TEXT)
        frame = read_frame(OUTPUT / f"world-clay-{pose}.png")
        sheet.paste(frame.resize((width, height), Image.Resampling.LANCZOS), (x, y + caption))
    return sheet


def main():
    original = read_frame(ROOT / "landing page.png")
    browser = read_frame(OUTPUT / "world-browser-home.png")
    artwork = {pose: read_frame(OUTPUT / f"world-orbit-{pose}.png") for pose in POSES}
    clay = {pose: read_frame(OUTPUT / f"world-clay-{pose}.png") for pose in POSES}
    paired_image(original, browser).save(OUTPUT / "world-comparison.png", optimize=True)
    Image.blend(original, browser, .5).save(OUTPUT / "world-overlay.png", optimize=True)
    orbit_contact_sheet(artwork).save(OUTPUT / "world-orbit-contact-sheet.png", optimize=True)
    orbit_contact_sheet(clay).save(OUTPUT / "world-clay-orbit-sheet.png", optimize=True)
    structural_sheet().save(OUTPUT / "world-structure-sheet.png", optimize=True)
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
        "orbit_captures_present": list(POSES),
        "landmark_alignment": landmark_report(original, browser),
        "four_pixel_target_passed": False,
        "limitations": [
            "The current reconstruction does not meet the four-pixel reference alignment target.",
            "Local patch matching searches only eight pixels in each direction; large departures cannot be measured by this search.",
            "Color similarity does not prove connected geometry, image alignment, or faithful perspective.",
            "Full cardinal views use automatic framing and are development inspection views, outside the supported orbit.",
        ],
    }
    (OUTPUT / "world-comparison-metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved world comparison, overlay, {len(regions)} paired crops, and three inspection sheets.")
    print(f"Mean absolute RGB difference: {report['global']['mae_0_255']:.3f} / 255.")
    print(f"Flagged local landmark patches: {len(report['landmark_alignment']['flagged_names'])} / {len(LANDMARKS)}.")
    print("Four-pixel fidelity target: not met.")


if __name__ == "__main__":
    main()
