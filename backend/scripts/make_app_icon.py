"""Generate the CallMind AI app icon as PNGs at all required sizes.

Source:  docs/app-icon.svg (vector master).
Output:
  docs/app-icon-1024.png    Google Play store listing
  docs/app-icon-512.png     high-res
  docs/app-icon-192.png     xxxhdpi
  docs/app-icon-48.png      mdpi launcher

The SVG is the master. This script is a Pillow-only fallback when no SVG
renderer (cairo / rsvg / inkscape) is available on the build machine.

Design:
  - Rounded-square indigo gradient background.
  - White phone handset glyph, slightly rotated.
  - Three AI sparkles around the handset.
"""
from __future__ import annotations

import math
import os
from PIL import Image, ImageDraw

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(OUT_DIR)            # backend/ -> docs/
OUT_DIR = os.path.join(OUT_DIR, "docs") if os.path.basename(OUT_DIR) == "backend" else OUT_DIR
# Robust path resolution:
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCS = os.path.join(ROOT, "docs")
os.makedirs(DOCS, exist_ok=True)

# Colours
BG_TOP = (79, 70, 229)     # #4F46E5
BG_BOT = (124, 58, 237)    # #7C3AED
PHONE = (255, 255, 255)
PHONE_SHADOW = (224, 231, 255)
INNER = (79, 70, 229)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient_bg(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            # diagonal gradient
            t = (x + y) / (2 * size)
            px[x, y] = lerp(BG_TOP, BG_BOT, t) + (255,)
    return img


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([(0, 0), (size - 1, size - 1)], radius=radius, fill=255)
    return mask


def draw_phone(draw: ImageDraw.ImageDraw, size: int) -> None:
    """Classic phone-handset glyph: a tilted rounded bar with circular ends.

    Rendered in design space (1024), then rotated + scaled. Keeps it crisp
    at any final icon size.
    """
    S = 1024

    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    # Body bar: tall and narrow so the rounded ends dominate the silhouette.
    bar_w = 200
    bar_x = (S - bar_w) // 2
    ld.rounded_rectangle(
        [bar_x, 240, bar_x + bar_w, S - 240],
        radius=bar_w // 2,
        fill=PHONE,
    )

    # Top earpiece disc (slightly wider than the bar)
    earpiece_r = 140
    ld.ellipse(
        [S // 2 - earpiece_r, 240 - 40,
         S // 2 + earpiece_r, 240 + 2 * earpiece_r],
        fill=PHONE,
    )
    # Inner speaker hole
    ld.ellipse(
        [S // 2 - 60, 240 + 30,
         S // 2 + 60, 240 + 150],
        fill=INNER,
    )

    # Bottom mouthpiece disc
    ld.ellipse(
        [S // 2 - earpiece_r, S - 240 - 2 * earpiece_r,
         S // 2 + earpiece_r, S - 240 + 40],
        fill=PHONE,
    )
    # Inner mic hole
    ld.ellipse(
        [S // 2 - 60, S - 240 - 150,
         S // 2 + 60, S - 240 - 30],
        fill=INNER,
    )

    # Tilt the whole handset.
    rotated = layer.rotate(-30, resample=Image.BICUBIC, expand=False)
    rotated = rotated.resize((size, size), Image.LANCZOS)
    draw._image.paste(rotated, (0, 0), rotated)


def draw_sparkle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, opacity: int = 255) -> None:
    """A 4-point sparkle (star) centred at (cx, cy) with radius r."""
    pts = []
    for i in range(8):
        angle = math.pi * i / 4 - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.35
        pts.append((cx + rr * math.cos(angle), cy + rr * math.sin(angle)))
    draw.polygon(pts, fill=PHONE)


def render(size: int) -> Image.Image:
    base = gradient_bg(size)
    mask = rounded_mask(size, radius=int(size * 0.22))
    base.putalpha(mask)

    # Soft inner glow
    glow = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([(size * 0.25, size * 0.35), (size * 0.75, size * 0.75)], fill=(255, 255, 255, 22))
    base = Image.alpha_composite(base, glow)

    # Phone glyph + sparkles — both drawn on a single layer.
    layer = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    d = ImageDraw.Draw(layer)
    draw_phone(d, size)
    # Sparkles
    s = size / 1024
    draw_sparkle(d, 760 * s, 280 * s, 70 * s)
    draw_sparkle(d, 880 * s, 420 * s, 36 * s)
    draw_sparkle(d, 240 * s, 780 * s, 30 * s)

    out = Image.alpha_composite(base, layer)
    return out


def main():
    for sz in (1024, 512, 192, 48):
        img = render(sz)
        path = os.path.join(DOCS, f"app-icon-{sz}.png")
        img.convert("RGB").save(path, "PNG", optimize=True)
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()