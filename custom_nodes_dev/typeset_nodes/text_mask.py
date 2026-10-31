"""TextToMask — rasterize a word/line with a bundled OFL font into a MASK and an IMAGE (white on black).

Used as an inpainting / control mask for the "inworld" text plate (text_plate.api.json) and anywhere a
text-shaped region is needed. Fonts ship in ./fonts (Anton, Inter variable; both SIL OFL 1.1).

Inputs: text (multiline ok), font, size (fraction of frame HEIGHT = em size), x/y (normalized center of
the text block), width/height (px), letter_spacing (em), padding (px dilation of the mask), align,
line_spacing (em), invert.
Outputs: MASK [1, H, W] float 0..1 and IMAGE [1, H, W, 3] (same content, RGB).
"""
import os

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# display name -> (file, variation name or None)
FONTS = {
    "Anton": ("Anton-Regular.ttf", None),
    "Inter Bold": ("Inter-Variable.ttf", "Bold"),
    "Inter Black": ("Inter-Variable.ttf", "Black"),
    "Inter SemiBold": ("Inter-Variable.ttf", "SemiBold"),
    "Inter Regular": ("Inter-Variable.ttf", "Regular"),
}


def load_font(name: str, px: int) -> ImageFont.FreeTypeFont:
    file, variation = FONTS.get(name, FONTS["Anton"])
    font = ImageFont.truetype(os.path.join(FONT_DIR, file), max(1, int(px)))
    if variation:
        try:
            font.set_variation_by_name(variation)
        except Exception:
            pass  # static fallback: FreeType without variation support
    return font


def _line_width(draw, font, line, spacing_px):
    if not line:
        return 0.0
    if spacing_px == 0:
        return draw.textlength(line, font=font)
    return sum(draw.textlength(ch, font=font) for ch in line) + spacing_px * (len(line) - 1)


def render_text(text, font_name, size, x, y, width, height, letter_spacing=0.0, padding=0,
                align="center", line_spacing=1.1):
    """Return a PIL 'L' image (white text on black) of size (width, height)."""
    px = max(1, int(round(size * height)))
    font = load_font(font_name, px)
    img = Image.new("L", (int(width), int(height)), 0)
    draw = ImageDraw.Draw(img)
    lines = text.replace("\r", "").split("\n") if text else [""]
    spacing_px = letter_spacing * px
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    advance = line_spacing * px
    block_h = advance * (len(lines) - 1) + line_h
    widths = [_line_width(draw, font, ln, spacing_px) for ln in lines]
    block_w = max(widths) if widths else 0
    left = x * width - block_w / 2.0
    top = y * height - block_h / 2.0
    for i, (ln, lw) in enumerate(zip(lines, widths)):
        if align == "left":
            lx = left
        elif align == "right":
            lx = left + block_w - lw
        else:
            lx = left + (block_w - lw) / 2.0
        ly = top + i * advance
        if spacing_px == 0:
            draw.text((lx, ly), ln, font=font, fill=255)
        else:
            cx = lx
            for ch in ln:
                draw.text((cx, ly), ch, font=font, fill=255)
                cx += draw.textlength(ch, font=font) + spacing_px
    if padding > 0:
        k = int(padding) * 2 + 1
        img = img.filter(ImageFilter.MaxFilter(k if k % 2 else k + 1))
    return img


class TextToMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"default": "NEON", "multiline": True}),
                "font": (list(FONTS.keys()), {"default": "Anton"}),
                "size": ("FLOAT", {"default": 0.2, "min": 0.01, "max": 2.0, "step": 0.005,
                                   "tooltip": "Em size as a fraction of the frame height."}),
                "x": ("FLOAT", {"default": 0.5, "min": -1.0, "max": 2.0, "step": 0.001,
                                "tooltip": "Normalized horizontal center of the text block."}),
                "y": ("FLOAT", {"default": 0.5, "min": -1.0, "max": 2.0, "step": 0.001,
                                "tooltip": "Normalized vertical center of the text block."}),
                "width": ("INT", {"default": 1024, "min": 8, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 576, "min": 8, "max": 8192, "step": 8}),
            },
            "optional": {
                "letter_spacing": ("FLOAT", {"default": 0.0, "min": -0.5, "max": 2.0, "step": 0.005,
                                             "tooltip": "Extra tracking in em."}),
                "padding": ("INT", {"default": 0, "min": 0, "max": 256, "step": 1,
                                    "tooltip": "Dilate the mask by this many pixels."}),
                "align": (["center", "left", "right"], {"default": "center"}),
                "line_spacing": ("FLOAT", {"default": 1.1, "min": 0.5, "max": 3.0, "step": 0.01}),
                "invert": ("BOOLEAN", {"default": False, "tooltip": "Black text on white instead."}),
            },
        }

    RETURN_TYPES = ("MASK", "IMAGE")
    RETURN_NAMES = ("mask", "image")
    FUNCTION = "run"
    CATEGORY = "typeset/text"

    def run(self, text, font, size, x, y, width, height, letter_spacing=0.0, padding=0,
            align="center", line_spacing=1.1, invert=False):
        img = render_text(text, font, size, x, y, width, height, letter_spacing, padding, align, line_spacing)
        arr = np.asarray(img, dtype=np.float32) / 255.0
        if invert:
            arr = 1.0 - arr
        mask = torch.from_numpy(arr)[None]                       # [1, H, W]
        image = mask[..., None].repeat(1, 1, 1, 3)               # [1, H, W, 3]
        return (mask, image)


NODE_CLASS_MAPPINGS = {"TextToMask": TextToMask}
NODE_DISPLAY_NAME_MAPPINGS = {"TextToMask": "Text → Mask (typeset)"}
