"""Generate sample sketch images for the 'Upload sketch' demo.

Produces a small library of test images at common sketch-tool scales:
  - clean line drawings (good for TRACE mode)
  - hand-sketch-style (good for INTERPRET mode)
  - dimensioned drawings (good for INTERPRET mode)

Run: python _generate.py
"""
from __future__ import annotations

import math
import os
import random

from PIL import Image, ImageDraw, ImageFont


HERE = os.path.dirname(os.path.abspath(__file__))


def _save(im: Image.Image, name: str) -> None:
    path = os.path.join(HERE, name)
    im.save(path, optimize=True)
    print("wrote", path)


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


# ---------- 1. clean circle (filled disc) ---------- #
def gen_circle():
    im = Image.new("RGB", (400, 400), "white")
    d = ImageDraw.Draw(im)
    d.ellipse([60, 60, 340, 340], outline="black", width=4, fill=None)
    d.text((150, 360), "Disc, ø ≈ 50 mm", fill="black", font=_font(16))
    _save(im, "01_circle.png")


# ---------- 2. rectangle with central hole ---------- #
def gen_rect_with_hole():
    im = Image.new("RGB", (480, 360), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([40, 60, 440, 300], outline="black", width=4)
    d.ellipse([200, 140, 280, 220], outline="black", width=4)
    d.text((150, 320), "Plate 80×48 mm  ·  hole ø 16 mm", fill="black", font=_font(15))
    _save(im, "02_plate_with_hole.png")


# ---------- 3. L-bracket ---------- #
def gen_l_bracket():
    im = Image.new("RGB", (400, 400), "white")
    d = ImageDraw.Draw(im)
    # L-shape outline
    pts = [(60, 60), (240, 60), (240, 200), (340, 200), (340, 340), (60, 340)]
    d.polygon(pts, outline="black", width=4, fill=None)
    # mounting holes (4)
    for x, y in [(140, 100), (140, 280), (290, 280), (200, 280)]:
        d.ellipse([x-12, y-12, x+12, y+12], outline="black", width=3)
    d.text((90, 360), "L-bracket, 4× ø 6 holes", fill="black", font=_font(15))
    _save(im, "03_l_bracket.png")


# ---------- 4. hand-sketched-style bracket (jittered lines) ---------- #
def gen_handsketch():
    im = Image.new("RGB", (500, 380), "white")
    d = ImageDraw.Draw(im)
    rng = random.Random(7)
    def jitter_line(p0, p1, k=1.4):
        # break a line into segments with small jitter to look hand-drawn
        n = max(8, int(math.hypot(p1[0]-p0[0], p1[1]-p0[1]) / 18))
        last = p0
        for i in range(1, n + 1):
            t = i / n
            x = p0[0] + (p1[0] - p0[0]) * t + rng.uniform(-k, k)
            y = p0[1] + (p1[1] - p0[1]) * t + rng.uniform(-k, k)
            d.line([last, (x, y)], fill="black", width=3)
            last = (x, y)
    # bracket outline
    corners = [(70, 70), (370, 70), (370, 200), (430, 200),
               (430, 320), (70, 320)]
    for i in range(len(corners)):
        jitter_line(corners[i], corners[(i + 1) % len(corners)])
    # bolt-hole circles, jittery
    for cx, cy in [(140, 130), (300, 130), (140, 280), (300, 280)]:
        for i in range(40):
            ang = 2 * math.pi * i / 40
            ang2 = 2 * math.pi * (i + 1) / 40
            r = 18 + rng.uniform(-1, 1)
            r2 = 18 + rng.uniform(-1, 1)
            d.line([(cx + r * math.cos(ang), cy + r * math.sin(ang)),
                    (cx + r2 * math.cos(ang2), cy + r2 * math.sin(ang2))],
                   fill="black", width=2)
    d.text((100, 340), "Hand-sketched L-bracket with 4 holes",
           fill="black", font=_font(14))
    _save(im, "04_handsketch_lbracket.png")


# ---------- 5. cross / plus shape ---------- #
def gen_cross():
    im = Image.new("RGB", (400, 400), "white")
    d = ImageDraw.Draw(im)
    pts = [(160, 60), (240, 60), (240, 160), (340, 160), (340, 240),
           (240, 240), (240, 340), (160, 340), (160, 240), (60, 240),
           (60, 160), (160, 160)]
    d.polygon(pts, outline="black", width=4, fill=None)
    d.text((110, 360), "Cross / plus, 80 mm overall", fill="black", font=_font(15))
    _save(im, "05_cross.png")


# ---------- 6. gear-tooth profile silhouette ---------- #
def gen_gear():
    im = Image.new("RGB", (440, 440), "white")
    d = ImageDraw.Draw(im)
    cx, cy = 220, 220
    n_teeth = 12
    root_r, tip_r = 140, 175
    pts = []
    for i in range(n_teeth * 4):
        f = i / (n_teeth * 4)
        ang = 2 * math.pi * f
        # alternate root / tip / tip / root pattern
        phase = i % 4
        r = root_r if phase in (0, 3) else tip_r
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    d.polygon(pts, outline="black", width=3, fill=None)
    d.ellipse([cx-22, cy-22, cx+22, cy+22], outline="black", width=3)
    d.text((110, 400), "Gear, 12 teeth, ø 25 bore", fill="black", font=_font(15))
    _save(im, "06_gear_outline.png")


def main():
    os.makedirs(HERE, exist_ok=True)
    gen_circle()
    gen_rect_with_hole()
    gen_l_bracket()
    gen_handsketch()
    gen_cross()
    gen_gear()
    print(f"\nGenerated 6 sample sketches in {HERE}")


if __name__ == "__main__":
    main()
