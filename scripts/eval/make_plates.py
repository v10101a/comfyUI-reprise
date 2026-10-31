#!/usr/bin/env python3
"""Make synthetic "text plate" test images with PIL for the LTX i2v / morph / image-edit evals.

Plates (written to --out, default ~/ComfyUI/input/eval/):
  neon_<W>x<H>.png      the word as a glowing pink neon sign on a dark brick wall
  chrome_<W>x<H>.png    the same word as brushed chrome letters bolted to the same wall (morph target)
  wall_<W>x<H>.png      the empty wall (background for the "add the word" image-edit test)

Usage: python3 scripts/eval/make_plates.py --word NEON --size 768x448 --size 1024x576
"""
import argparse
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

FONT_CANDIDATES = ["/System/Library/Fonts/Supplemental/Impact.ttf",
                   "/System/Library/Fonts/Supplemental/Arial Black.ttf",
                   "/System/Library/Fonts/Supplemental/Verdana Bold.ttf"]


def font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def brick_wall(w, h, seed=1):
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), (38, 30, 28))
    d = ImageDraw.Draw(img)
    bh = max(18, h // 18)
    bw = bh * 2
    y = 0
    row = 0
    while y < h:
        x = -(bw // 2) if row % 2 else 0
        while x < w:
            c = 55 + rnd.randint(-12, 12)
            d.rectangle([x + 2, y + 2, x + bw - 2, y + bh - 2], fill=(c + rnd.randint(0, 10), c - 18, c - 22))
            x += bw
        y += bh
        row += 1
    # grime / vignette
    noise = Image.effect_noise((w, h), 18).convert("RGB")
    img = ImageChops.multiply(img, Image.blend(Image.new("RGB", (w, h), (255, 255, 255)), noise, 0.35))
    vign = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vign).ellipse([-w * 0.2, -h * 0.4, w * 1.2, h * 1.4], fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(w // 6))
    img = Image.composite(img, Image.new("RGB", (w, h), (8, 6, 8)), vign)
    return img


def text_mask(w, h, word, scale=0.62):
    f = font(int(h * scale))
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    bbox = d.textbbox((0, 0), word, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((w - tw) / 2 - bbox[0], (h - th) / 2 - bbox[1]), word, font=f, fill=255)
    return m


def neon(wall, word):
    w, h = wall.size
    core = text_mask(w, h, word)
    # neon tube = outline of the glyphs, not a filled face
    inner = core.filter(ImageFilter.MinFilter(max(3, h // 56) | 1))
    tube = ImageChops.subtract(core, inner)
    img = wall.copy()
    pink = (255, 70, 190)
    # wall glow (wide), then medium halo, then tube, then hot white core
    for radius, alpha, col in ((h // 7, 0.55, (255, 40, 160)), (h // 22, 0.85, pink)):
        glow = tube.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: min(255, int(v * 2.2 * alpha)))
        img = Image.composite(Image.new("RGB", (w, h), col), img, glow)
    img = Image.composite(Image.new("RGB", (w, h), pink), img, tube.filter(ImageFilter.GaussianBlur(1.2)))
    hot = tube.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    img = Image.composite(Image.new("RGB", (w, h), (255, 225, 245)), img, hot)
    # floor reflection smear at the bottom
    refl = img.crop((0, h // 2, w, h)).transpose(Image.FLIP_TOP_BOTTOM).filter(ImageFilter.GaussianBlur(6))
    fade = Image.linear_gradient("L").resize((w, h // 2)).point(lambda v: int((255 - v) * 0.25))
    img.paste(Image.blend(img.crop((0, h // 2, w, h)), refl, 0.5), (0, h // 2), fade)
    return img


def chrome(wall, word):
    w, h = wall.size
    core = text_mask(w, h, word)
    img = wall.copy()
    shadow = core.filter(ImageFilter.GaussianBlur(h // 40))
    img = Image.composite(Image.new("RGB", (w, h), (5, 4, 6)), img, ImageChops.offset(shadow, h // 60, h // 45))
    grad = Image.linear_gradient("L").resize((w, h))
    steel = Image.merge("RGB", (grad.point(lambda v: 120 + v // 3), grad.point(lambda v: 125 + v // 3), grad.point(lambda v: 135 + v // 3)))
    band = Image.new("L", (w, h), 0)
    ImageDraw.Draw(band).polygon([(0, h * 0.42), (w, h * 0.30), (w, h * 0.40), (0, h * 0.52)], fill=255)
    steel = Image.composite(Image.new("RGB", (w, h), (235, 240, 245)), steel, band.filter(ImageFilter.GaussianBlur(4)))
    img = Image.composite(steel, img, core)
    bevel = ImageChops.subtract(core, ImageChops.offset(core, 2, 3))
    img = Image.composite(Image.new("RGB", (w, h), (250, 250, 255)), img, bevel)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--word", default="NEON")
    ap.add_argument("--size", action="append", default=None)
    ap.add_argument("--out", default=os.path.expanduser("~/ComfyUI/input/eval"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for s in (a.size or ["768x448", "1024x576"]):
        w, h = map(int, s.split("x"))
        wall = brick_wall(w, h)
        wall.save(os.path.join(a.out, f"wall_{w}x{h}.png"))
        neon(wall, a.word).save(os.path.join(a.out, f"neon_{w}x{h}.png"))
        chrome(wall, a.word).save(os.path.join(a.out, f"chrome_{w}x{h}.png"))
        print("wrote", s, "->", a.out)


if __name__ == "__main__":
    main()
