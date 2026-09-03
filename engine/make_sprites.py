#!/usr/bin/env python3
"""make_sprites.py — Dynamically generate the Godot player sprite sheet
from the dashboard's Among Us bean design.

The bean shapes are ported from dashboard/src/components/landing/AmongUsBean.vue
(the same SVG used across the website), including the exact body path.
The palette is parsed straight out of among-i/Scripts/Server.gd's
AGENT_COLORS const, so the sheet always matches the renderer's colors —
one source of truth, generated, never hand-edited.

Sheet layout (used by Player.tscn / player.gd):
    columns  = 4 frames
    rows     = 3 per color  (0 idle · 1 walk · 2 dead)
    bands    = one per AGENT_COLORS entry, stacked vertically
    color_band (set by Server.gd at spawn) shifts the row base:
        row = color_band * 3 + pose_row

Usage:
    python make_sprites.py                     # write ../among-i/sprites/beans.png
    python make_sprites.py --preview out.png   # also dump a contact-sheet preview
    python make_sprites.py --colors '#C51111,#132ED2' --frame-size 96
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("[make_sprites] Pillow is required: pip install pillow")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

DEFAULT_SERVER_GD = os.path.join(REPO, "among-i", "Scripts", "Server.gd")
DEFAULT_OUT = os.path.join(REPO, "among-i", "sprites", "beans.png")

# Grid layout — must match Player.tscn (hframes/vframes) and player.gd rows
FRAMES = 4          # columns
ROWS_PER_COLOR = 3  # 0 idle · 1 walk · 2 dead

FALLBACK_COLORS = ["#C51111", "#132ED2", "#117F2D", "#ED54BB", "#EF7D0E",
                   "#C8CD00", "#3F474E", "#D85A30", "#378ADD", "#1D9E75"]

# Body silhouette — the exact path from AmongUsBean.vue (viewBox 0 0 120 160):
#   M22,138 Q10,138 10,116 L10,64 Q10,6 62,6 Q114,6 114,64
#   L114,108 Q114,140 92,140 Z
# (flat bottom with rounded corners, round top — NOT a symmetric egg)
BODY_PATH = [
    ("M", [(22, 138)]),
    ("Q", [(10, 138), (10, 116)]),
    ("L", [(10, 64)]),
    ("Q", [(10, 6), (62, 6)]),
    ("Q", [(114, 6), (114, 64)]),
    ("L", [(114, 108)]),
    ("Q", [(114, 140), (92, 140)]),
    ("Z", []),
]

# Other shapes from the same SVG markup
BACKPACK = (2, 58, 28, 116)        # backpack behind the body
LEG_PIVOTS = [(35, 128), (75, 128)]  # top-center of each leg (viewBox units)
LEG_W, LEG_H = 18, 28              # leg size in viewBox units
VISOR = (48, 31, 112, 73)          # light-blue visor
VISOR_HI = (81, 39, 99, 49)        # visor highlight
SHADOW = (22, 148, 98, 158)        # ground shadow
STROKE = 5                         # body outline width in viewBox units


def shade(hex_color: str, percent: float) -> str:
    """Lighten (+percent) or darken (-percent) a #RRGGBB color.
    Mirrors the shade() helper in AmongUsBean.vue."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c + c for c in h)
    num = int(h, 16)
    r = min(255, max(0, (num >> 16) + round(255 * percent)))
    g = min(255, max(0, ((num >> 8) & 0xFF) + round(255 * percent)))
    b = min(255, max(0, (num & 0xFF) + round(255 * percent)))
    return f"#{r:02X}{g:02X}{b:02X}"


def colors_from_server_gd(path: str) -> list[str]:
    """Parse `const AGENT_COLORS = [...]` out of Server.gd so the sheet
    always matches the renderer's palette."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"const AGENT_COLORS\s*=\s*\[([^\]]*)\]", text)
        if m:
            found = re.findall(r'"#([0-9A-Fa-f]{6})"', m.group(1))
            if found:
                return ["#" + c.upper() for c in found]
    except OSError as e:
        print(f"[make_sprites] Could not read {path}: {e}")
    print("[make_sprites] Falling back to built-in palette")
    return list(FALLBACK_COLORS)


def _quad_points(p0, c, p1, n=24):
    """Sample a quadratic Bezier p0 → p1 with control c."""
    pts = []
    for i in range(n + 1):
        t = i / n
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t ** 2 * p1[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t ** 2 * p1[1]
        pts.append((x, y))
    return pts


def body_outline() -> list[tuple[float, float]]:
    """The bean silhouette as a flat polygon in viewBox coordinates."""
    pts = [BODY_PATH[0][1][0]]
    for kind, args in BODY_PATH[1:]:
        if kind == "Q":
            c, p1 = args
            pts.extend(_quad_points(pts[-1], c, p1)[1:])
        elif kind == "L":
            pts.append(args[0])
    return pts


def draw_bean(frame: int, color: str, pose: str, frame_idx: int) -> Image.Image:
    """Draw one bean into a transparent frame-sized image.

    pose: "idle" | "walk" | "dead"
    frame_idx: 0..FRAMES-1 (drives leg swing / bob)

    The bean is anchored with its FEET at the bottom edge of the frame,
    so a centered sprite stands on its tile instead of sinking into the
    row below.
    """
    img = Image.new("RGBA", (frame, frame), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Art scale tracks the frame size (0.75 at the 128px default)
    s = frame * 0.75 / 128.0
    ox = (frame - 120 * s) / 2.0            # centered horizontally
    oy = frame - 2 - 160 * s                # feet at the cell bottom

    body_fill = color
    body_line = shade(color, -0.5)
    dark = shade(color, -0.35)
    darker = shade(color, -0.5)

    # Pose offsets
    bob = 0
    # (angle_deg, lift_units) per leg — angle sways the leg around its
    # pivot, lift shortens it (foot off the ground). viewBox y is DOWN,
    # so a positive angle swings the LEFT leg's foot outward (left).
    leg_pose = [(0.0, 0), (0.0, 0)]
    if pose == "walk":
        bob = 2 * s if frame_idx in (1, 3) else 0
        if frame_idx == 1:
            leg_pose = [(14.0, 4), (0.0, 0)]    # left foot out + lifted
        elif frame_idx == 3:
            leg_pose = [(0.0, 0), (-14.0, 4)]   # right foot out + lifted
    elif pose == "idle":
        # Breathing cycle: rest, sink, rest, rise — player.gd cycles the
        # 4 columns slowly while standing still.
        bob = (0, 2, 0, -2)[frame_idx % 4]

    def r(bbox):
        return [bbox[0] * s + ox, bbox[1] * s + oy + bob,
                bbox[2] * s + ox, bbox[3] * s + oy + bob]

    # Ground shadow (first, so everything draws on top)
    d.ellipse(r(SHADOW), fill=(0, 0, 0, 72))

    # Backpack (behind the body)
    d.rounded_rectangle(r(BACKPACK), radius=13 * s, fill=darker)

    # Legs — BEHIND the body, like the SVG's paint order: the body
    # silhouette covers their top halves, only the feet show below.
    # Walk frames swing each leg around its top pivot (angled stride)
    # and lift one foot off the ground.
    for pivot, (angle, lift) in zip(LEG_PIVOTS, leg_pose):
        a = math.radians(angle)
        half = LEG_W / 2.0
        # local corners in viewBox coords (y DOWN): the leg hangs from
        # its top-center pivot; lift shortens it (foot rises)
        corners = [(-half, LEG_H - lift), (half, LEG_H - lift),
                   (half, 0), (-half, 0)]
        pts = []
        for x, y in corners:
            rx = pivot[0] + x * math.cos(a) - y * math.sin(a)
            ry = pivot[1] + x * math.sin(a) + y * math.cos(a)
            pts.append((rx * s + ox, ry * s + oy + bob))
        d.polygon(pts, fill=dark)

    # Body — the SVG's exact silhouette. Paint order matches the SVG:
    # fill first, then the 5-unit stroke on top (stroke-linejoin round),
    # so the full stroke width shows instead of being half-covered.
    poly = [(x * s + ox, y * s + oy + bob) for x, y in body_outline()]
    d.polygon(poly, fill=body_fill)
    d.line(poly + [poly[0]], fill=body_line,
           width=max(2, round(STROKE * s)), joint="curve")

    # Visor — light blue, exactly like the dashboard bean
    # (SVG stroke-width 4, drawn on top of the fill by Pillow)
    d.ellipse(r(VISOR), fill="#bfe9ff", outline="#5b8aa8",
              width=max(2, round(4 * s)))
    d.ellipse(r(VISOR_HI), fill=(255, 255, 255, 180))

    # Dead pose: the whole bean lying on its side (head left, feet right).
    # The standing art is feet-anchored, so rotating around the cell center
    # would shift it — re-crop the rotated art and center it again.
    if pose == "dead":
        img = img.rotate(90)
        bbox = img.getbbox()
        if bbox:
            art = img.crop(bbox)
            centered = Image.new("RGBA", (frame, frame), (0, 0, 0, 0))
            centered.paste(art, ((frame - art.width) // 2,
                                 (frame - art.height) // 2))
            img = centered

    return img


def build_sheet(colors: list[str], frame: int) -> Image.Image:
    """Compose the full sheet: FRAMES cols × (ROWS_PER_COLOR × colors) rows."""
    sheet = Image.new("RGBA", (frame * FRAMES, frame * ROWS_PER_COLOR * len(colors)),
                      (0, 0, 0, 0))
    poses = ["idle", "walk", "dead"]
    for band, color in enumerate(colors):
        for row, pose in enumerate(poses):
            for f in range(FRAMES):
                cell = draw_bean(frame, color, pose, f)
                sheet.paste(cell, (f * frame, (band * ROWS_PER_COLOR + row) * frame))
        print(f"[make_sprites] band {band:>2}  {color}  "
              f"rows {band * ROWS_PER_COLOR}..{band * ROWS_PER_COLOR + ROWS_PER_COLOR - 1}")
    return sheet


def preview_sheet(sheet: Image.Image, frame: int, colors: list[str], out_path: str):
    """Contact sheet: colors as columns, poses as labeled rows."""
    from PIL import ImageDraw as _D
    pad, label_h = 8, 24
    cell = frame + pad * 2
    cols, rows = len(colors), ROWS_PER_COLOR
    prev = Image.new("RGBA", (cols * cell, rows * cell + label_h), (10, 15, 10, 255))
    d = _D.Draw(prev)
    pose_names = ["idle", "walk", "dead"]
    for band in range(cols):
        for row in range(rows):
            c = sheet.crop((0, (band * ROWS_PER_COLOR + row) * frame,
                            FRAMES * frame, (band * ROWS_PER_COLOR + row + 1) * frame))
            prev.paste(c, (band * cell + pad, label_h + row * cell + pad))
            d.text((band * cell + pad + frame - 60, label_h + row * cell + pad),
                   f"{band}:{pose_names[row]}", fill="#8AFF6A")
    prev.save(out_path)
    print(f"[make_sprites] preview → {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate the Godot bean sprite sheet")
    parser.add_argument("--colors", default=None,
                        help="Comma-separated #hex colors (default: AGENT_COLORS from Server.gd)")
    parser.add_argument("--server-gd", default=DEFAULT_SERVER_GD,
                        help="Path to Server.gd to read AGENT_COLORS from")
    parser.add_argument("--frame-size", type=int, default=128,
                        help="Pixel size of one animation frame (default 128)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output PNG path")
    parser.add_argument("--preview", default=None, metavar="PATH",
                        help="Also write a labeled contact-sheet preview")
    args = parser.parse_args()

    colors = (args.colors.split(",") if args.colors
              else colors_from_server_gd(args.server_gd))
    frame = args.frame_size

    sheet = build_sheet(colors, frame)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    sheet.save(args.out)
    print(f"[make_sprites] wrote {args.out} "
          f"({sheet.size[0]}x{sheet.size[1]}, "
          f"{FRAMES} frames x {ROWS_PER_COLOR} rows x {len(colors)} colors)")

    if args.preview:
        preview_sheet(sheet, frame, colors, args.preview)


if __name__ == "__main__":
    main()
