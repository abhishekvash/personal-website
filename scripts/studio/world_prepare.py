"""Separate the observatory's painted surfaces before assigning their artwork.

The telescope and the room behind it occupy different meshes. Their source
images therefore need different foreground masks, even when their authored
coordinates overlap. Missing paint is extended from the original swatches.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "public/scene/textures"
SIZE = (1536, 1024)
OUTER_RIM = [(746, 57), (776, 60), (806, 77), (834, 107), (848, 142),
             (850, 171), (841, 199), (820, 218), (792, 226), (762, 221),
             (733, 203), (709, 177), (695, 150), (689, 116), (696, 87), (719, 67)]
INNER_RIM = [(746, 77), (770, 78), (796, 91), (818, 115), (833, 143),
             (835, 169), (825, 191), (808, 205), (783, 211), (758, 203),
             (734, 187), (716, 164), (707, 139), (705, 113), (711, 94), (726, 82)]


def _contour_mask(points):
    """Rasterize a smooth closed contour with subpixel edges."""
    curve = []
    for index, point in enumerate(points):
        a, b, c, d = (np.asarray(points[(index + offset) % len(points)], dtype=float)
                      for offset in (-1, 0, 1, 2))
        for step in range(12):
            t = step / 12
            position = .5 * ((2 * b) + (-a + c) * t +
                             (2 * a - 5 * b + 4 * c - d) * t * t +
                             (-a + 3 * b - 3 * c + d) * t * t * t)
            curve.append(tuple(position * 4))
    mask = Image.new("L", (SIZE[0] * 4, SIZE[1] * 4))
    ImageDraw.Draw(mask).polygon(curve, fill=255)
    return mask.resize(SIZE, Image.Resampling.LANCZOS)


def _swatch(name):
    sample = np.asarray(Image.open(OUT / (name + ".png")).convert("RGB"))
    yy, xx = np.indices((SIZE[1], SIZE[0]))
    return Image.fromarray(sample[yy % sample.shape[0], xx % sample.shape[1]])


def _foreground_mask():
    mask = Image.new("L", SIZE)
    draw = ImageDraw.Draw(mask)
    # Each silhouette belongs to the modeled telescope, its cradle, or tripod.
    draw.polygon([(727, 113), (737, 108), (749, 115), (820, 149),
                  (821, 164), (811, 173), (795, 165), (733, 138), (726, 128)], fill=255)
    draw.line([(773, 151), (775, 180)], fill=255, width=16)
    draw.ellipse((763, 165, 787, 182), fill=255)
    for foot in ((751, 205), (780, 212), (799, 202)):
        draw.line([(774, 174), foot], fill=255, width=10)
        draw.ellipse((foot[0] - 5, foot[1] - 3, foot[0] + 5, foot[1] + 3), fill=255)
    draw.polygon([(764, 170), (784, 169), (806, 214), (743, 219)], fill=255)
    return mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(.7))


def prepare_world_observatory():
    """Write independent full-size source views for shell, rim, and starfield."""
    source = Image.open(ROOT / "landing page.png").convert("RGB")
    if source.size != SIZE:
        raise ValueError("The observatory source must retain its 1536 × 1024 coordinates.")
    OUT.mkdir(parents=True, exist_ok=True)
    cream = _swatch("cream")
    # This small source patch contains only the painted navy grain. The general
    # ink swatch includes bright stars, which would repeat behind the telescope.
    sample = np.asarray(source.crop((713, 139, 723, 145)))
    random = np.random.default_rng(4317)
    grain = sample.reshape(-1, 3)[random.integers(len(sample.reshape(-1, 3)), size=(SIZE[1], SIZE[0]))]
    ink = Image.fromarray(grain).filter(ImageFilter.GaussianBlur(.35))
    outside, inside = _contour_mask(OUTER_RIM), _contour_mask(INNER_RIM)

    # Preserve the optical stars exactly where the source exposes them. No
    # telescope pixels remain on the room behind the actual telescope meshes.
    pixels = np.asarray(source, dtype=np.int16)
    navy = (pixels[:, :, 2] > pixels[:, :, 0] * 1.2) & (pixels[:, :, 0] < 100)
    navy_mask = Image.fromarray((navy * 255).astype(np.uint8))
    # Closing small gaps retains stars while rejecting the wide warm rim. The
    # inner erosion keeps antialiased cream edge pixels out of the dark room.
    navy_mask = navy_mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(11))
    star_mask = Image.fromarray(np.minimum(np.asarray(inside), np.asarray(navy_mask)))
    stars = Image.composite(source, ink, star_mask)
    stars = Image.composite(ink, stars, _foreground_mask())
    stars.save(OUT / "observatory-stars.png", optimize=True)

    # A separate ring view prevents chamber or prop masks from consuming the
    # rim's cream paint. Beyond its contour, newly exposed lip remains cream.
    annulus = Image.fromarray(np.maximum(0, np.asarray(outside, dtype=np.int16) -
                                       np.asarray(inside, dtype=np.int16)).astype(np.uint8))
    warm = (pixels[:, :, 0] > 100) & (pixels[:, :, 0] > pixels[:, :, 2] * 1.05)
    warm_mask = Image.fromarray((warm * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))
    annulus = Image.fromarray(np.minimum(np.asarray(annulus), np.asarray(warm_mask)))
    rim = Image.composite(source, cream, annulus)
    rim.save(OUT / "observatory-rim.png", optimize=True)

    # The top and rear of the hemisphere cannot inherit the source aperture.
    shell = Image.composite(cream, source, outside.filter(ImageFilter.MaxFilter(5)))
    shell.save(OUT / "observatory-shell.png", optimize=True)
    print("Prepared separate observatory starfield, rim, and exterior source views.")


if __name__ == "__main__":
    prepare_world_observatory()
