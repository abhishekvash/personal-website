"""Generate visual review artifacts from the reference and captured browser frames."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets/studio"
SIZE = (1536, 1024)
REGIONS = {
    "observatory": ("Observatory", (570, 20, 923, 287)),
    "gaming": ("Gaming", (482, 296, 988, 524)),
    "recording": ("Recording", (480, 504, 979, 696)),
    "workstation": ("Workstation", (466, 713, 769, 949)),
    "kitchen": ("Kitchen", (775, 680, 1090, 911)),
    "bonsai": ("Bonsai", (947, 0, 1536, 831)),
    "table-feet": ("Table + feet", (240, 823, 1138, 1024)),
}
POSES = (
    "left", "right", "up", "down",
    "top-left", "top-right", "bottom-left", "bottom-right",
)
LANDMARKS = (
    ("Dome cap", 729, 37), ("Aperture top", 747, 77), ("Telescope lens", 741, 125),
    ("Aerial", 549, 187), ("Upper roof", 396, 280), ("Upper port", 435, 370),
    ("Gaming screen", 725, 361), ("Gaming chair", 674, 396), ("Mic", 635, 584),
    ("Lamp", 682, 550), ("Console", 867, 605), ("Middle port", 405, 558),
    ("Workscreen", 537, 781), ("Pan", 858, 779), ("Pot", 953, 771),
    ("Drawer", 999, 837), ("Foot", 471, 984), ("Planter port", 1180, 701),
    ("Planter base", 1314, 820),
)
BACKGROUND = "#f4f1eb"
TEXT = "#34312d"


def font(size):
    for candidate in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def read_frame(path):
    with Image.open(path) as image:
        if image.size != SIZE:
            raise ValueError(
                f"{path} is {image.width} × {image.height}; expected 1536 × 1024. "
                "Capture the complete canvas at device pixel ratio 1. "
                "Comparison does not resize or realign input frames."
            )
        return image.convert("RGB")


def paired_image(original, browser, title=None, scale=1):
    if scale != 1:
        enlarged = (original.width * scale, original.height * scale)
        original = original.resize(enlarged, Image.Resampling.NEAREST)
        browser = browser.resize(enlarged, Image.Resampling.NEAREST)
    margin, gap = 16, 16
    title_height = 36 if title else 0
    label_height = 36
    top = margin + title_height + label_height
    sheet = Image.new(
        "RGB", (original.width * 2 + margin * 2 + gap, original.height + top + margin),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    if title:
        draw.text((margin, margin), title, fill=TEXT, font=font(22))
    right = margin + original.width + gap
    for x, label in ((margin, "Original"), (right, "Browser")):
        draw.text((x, margin + title_height), label, fill=TEXT, font=font(20))
    sheet.paste(original, (margin, top))
    sheet.paste(browser, (right, top))
    return sheet


def appearance_metrics(original, browser):
    difference = np.abs(
        np.asarray(original, dtype=np.int16) - np.asarray(browser, dtype=np.int16)
    )
    per_pixel = difference.mean(axis=2)
    return {
        "mae_0_255": round(float(difference.mean()), 6),
        "percent_pixels_mean_absdiff_lt_12": round(float((per_pixel < 12).mean() * 100), 6),
        "pixel_count": original.width * original.height,
    }


def landmark_report(original, browser):
    source = np.asarray(original, dtype=np.int16)
    rendered = np.asarray(browser, dtype=np.int16)
    results = []
    for name, x, y in LANDMARKS:
        patch = source[y - 10:y + 10, x - 10:x + 10]
        candidates = []
        for dy in range(-8, 9):
            for dx in range(-8, 9):
                candidate = rendered[y + dy - 10:y + dy + 10, x + dx - 10:x + dx + 10]
                if candidate.shape != patch.shape:
                    continue
                error = float(np.abs(patch - candidate).mean())
                candidates.append((error, dx * dx + dy * dy, dx, dy))
        candidates.sort()
        best, runner_up = candidates[:2]
        error, _, dx, dy = best
        distance = math.hypot(dx, dy)
        reasons = []
        if distance > 4:
            reasons.append("Best-match displacement exceeds 4 pixels.")
        if error > 25:
            reasons.append("Best-match patch MAE exceeds 25 / 255.")
        results.append({
            "name": name,
            "source_center_xy": [x, y],
            "best_browser_center_xy": [x + dx, y + dy],
            "best_translation_xy": [dx, dy],
            "displacement_px": round(distance, 6),
            "best_patch_mae_0_255": round(error, 6),
            "second_best_patch_mae_0_255": round(runner_up[0], 6),
            "confidence_margin_mae": round(runner_up[0] - error, 6),
            "flagged": bool(reasons),
            "reasons": reasons,
        })
    return {
        "method": (
            "For each original 20 × 20 RGB patch, compare browser patches at integer "
            "translations from -8 through +8 pixels on each axis. Choose minimum MAE; "
            "ties prefer the smallest Euclidean displacement."
        ),
        "scope": "Sampled image-feature alignment only; not full-silhouette alignment or 3D depth.",
        "confidence_note": (
            "Confidence margin is second-best MAE minus best MAE. A larger gap indicates "
            "a more distinct match; it is not a calibrated probability."
        ),
        "flag_thresholds": {"displacement_px_greater_than": 4, "patch_mae_greater_than": 25},
        "landmarks": results,
        "flagged_names": [result["name"] for result in results if result["flagged"]],
    }


def orbit_contact_sheet(frames):
    width, height = 384, 256
    margin, gap, caption = 16, 12, 30
    header = 42
    sheet = Image.new(
        "RGB", (4 * width + 3 * gap + 2 * margin,
                2 * (height + caption) + gap + 2 * margin + header),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, margin), "Orbit boundary views", fill=TEXT, font=font(24))
    for index, pose in enumerate(POSES):
        x = margin + (index % 4) * (width + gap)
        y = margin + header + (index // 4) * (height + caption + gap)
        draw.text((x, y), pose.replace("-", " ").title(), fill=TEXT, font=font(18))
        if pose in frames:
            preview = frames[pose].resize((width, height), Image.Resampling.LANCZOS)
            sheet.paste(preview, (x, y + caption))
        else:
            draw.rectangle((x, y + caption, x + width - 1, y + caption + height - 1),
                           fill="#e3dfd7")
            draw.text((x + 16, y + caption + 16), "Capture unavailable", fill=TEXT, font=font(18))
    return sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landmarks", action="store_true",
                        help="Include local patch matching for 19 reference landmarks.")
    args = parser.parse_args()
    original = read_frame(ROOT / "landing page.png")
    browser = read_frame(OUTPUT / "browser-home.png")
    orbit_frames = {
        pose: read_frame(OUTPUT / f"orbit-{pose}.png")
        for pose in POSES if (OUTPUT / f"orbit-{pose}.png").is_file()
    }
    crops = OUTPUT / "comparison-crops"
    crops.mkdir(parents=True, exist_ok=True)

    paired_image(original, browser).save(OUTPUT / "comparison.png", optimize=True)
    Image.blend(original, browser, .5).save(OUTPUT / "overlay.png", optimize=True)
    difference = np.abs(
        np.asarray(original, dtype=np.int16) - np.asarray(browser, dtype=np.int16)
    )
    amplified = np.clip(difference * 4, 0, 255).astype(np.uint8)
    Image.fromarray(amplified).save(OUTPUT / "difference.png", optimize=True)

    report = {
        "source": "landing page.png",
        "browser_capture": "assets/studio/browser-home.png",
        "frame_size": list(SIZE),
        "measurement": "Absolute differences of RGB channels in 8-bit sRGB code values.",
        "pixel_threshold": "Mean absolute RGB-channel difference strictly below 12.",
        "proves_four_pixel_alignment": False,
        "alignment_note": (
            "Appearance metrics are not proof of alignment within 4 pixels. "
            "Optional patch matching measures sampled image features only, "
            "not full silhouettes or 3D depth. Inspect regional crops and orbit views separately."
        ),
        "global": appearance_metrics(original, browser),
        "regions": {},
        "orbit_captures_present": [pose for pose in POSES if pose in orbit_frames],
        "orbit_captures_missing": [pose for pose in POSES if pose not in orbit_frames],
    }
    for name, (label, bounds) in REGIONS.items():
        original_crop = original.crop(bounds)
        browser_crop = browser.crop(bounds)
        paired_image(original_crop, browser_crop, f"{label} · 2×", scale=2).save(
            crops / f"{name}.png", optimize=True,
        )
        report["regions"][name] = {
            "label": label,
            "bounds_xyxy": list(bounds),
            **appearance_metrics(original_crop, browser_crop),
        }
    if orbit_frames:
        orbit_contact_sheet(orbit_frames).save(OUTPUT / "orbit-contact-sheet.png", optimize=True)
    if args.landmarks:
        report["landmark_alignment"] = landmark_report(original, browser)
    (OUTPUT / "comparison-metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Generated comparison, overlay, 4× difference, and {len(REGIONS)} enlarged crop pairs.")
    print(f"Global MAE: {report['global']['mae_0_255']:.4f} / 255.")
    print(f"Pixels with mean absolute difference < 12: "
          f"{report['global']['percent_pixels_mean_absdiff_lt_12']:.2f}%.")
    print(f"Orbit captures: {len(orbit_frames)} / {len(POSES)}.")
    print("These appearance metrics do not prove alignment within 4 pixels.")
    if args.landmarks:
        flagged = report["landmark_alignment"]["flagged_names"]
        print(f"Landmark patches flagged for review: {len(flagged)} / {len(LANDMARKS)}.")
        for landmark in report["landmark_alignment"]["landmarks"]:
            if landmark["flagged"]:
                print(f"  {landmark['name']}: shift {landmark['displacement_px']:.2f}px, "
                      f"patch MAE {landmark['best_patch_mae_0_255']:.2f} / 255.")


if __name__ == "__main__":
    main()
