"""TypesetLook / TypesetGrade: the Reprise look (text) and grade (footage) as ComfyUI nodes.

Presets come from look_presets.json, a copy of apps/web/src/look-presets.json (a test keeps them equal).
  TypesetLook   preset + the full param set as widgets -> look_json ({"id", "overrides"}, the exact shape of
                project.look, so it can be pasted into a project or fed to TypesetTextPlate) + a type preview.
  TypesetGrade  IMAGE batch + grade preset/amount/params (+ optional beats JSON for the flash) -> graded IMAGE +
                grade_json ({"id", "amount", "overrides"} = project.grade). Same maths as the web renderer's
                paintVideo (colour tint keeping luminance, halation, photocopy mono with beat flash, film grain);
                numerically close to the browser, not bit-identical.
Pure numpy/Pillow helpers (resolve_look, look_param_patch, resolve_grade, grade_frames) are importable without torch.
"""
import json
import os
import re
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")


@lru_cache(maxsize=1)
def presets():
    with open(os.path.join(HERE, "look_presets.json"), encoding="utf-8") as f:
        return json.load(f)


LOOK_IDS = lambda: list(presets()["looks"].keys())          # noqa: E731
GRADE_IDS = lambda: list(presets()["grades"].keys())        # noqa: E731

# family -> {style: file}; weights come from the variable axes where the file has them.
FONT_FILES = {
    "Inter": {"normal": "Inter-Variable.ttf"},
    "Anton": {"normal": "Anton-Regular.ttf"},
    "Archivo Narrow": {"normal": "ArchivoNarrow-Variable.ttf"},
    "Big Shoulders Display": {"normal": "BigShouldersDisplay-Variable.ttf"},
    "Bebas Neue": {"normal": "BebasNeue-Regular.ttf"},
    "Silkscreen": {"normal": "Silkscreen-Regular.ttf"},
    "Pinyon Script": {"normal": "PinyonScript-Regular.ttf"},
    "Instrument Serif": {"normal": "InstrumentSerif-Regular.ttf", "italic": "InstrumentSerif-Italic.ttf"},
    "Newsreader": {"normal": "Newsreader-Variable.ttf", "italic": "Newsreader-Italic-Variable.ttf"},
    "IBM Plex Mono": {"normal": "IBMPlexMono-Regular.ttf"},
    "Sixtyfour": {"normal": "Sixtyfour-Variable.ttf"},
    "Space Mono": {"normal": "SpaceMono-Bold.ttf"},
    "Permanent Marker": {"normal": "PermanentMarker-Regular.ttf"},
    "Rubik Wet Paint": {"normal": "RubikWetPaint-Regular.ttf"},
}
FAMILIES = list(FONT_FILES.keys())
DEFAULT_WEIGHT = {"Inter": 800, "Archivo Narrow": 500, "Big Shoulders Display": 900, "Space Mono": 700}

# ---------------------------------------------------------------- look params (mirror of looks.ts LOOK_PARAMS)
PARAMS = ["boxes", "note", "noteGlow", "ink", "accent", "card", "cards", "font", "body", "case", "layout", "scale", "motion", "glow",
          "flicker", "drips", "light", "outline", "halo", "soft", "tubes", "scroll", "hooks", "fill", "cell", "backing",
          "dots", "dot", "gap", "pad", "cardGap"]
_DEEP = ("palette", "font", "optics", "verse", "fill", "raster")
FILL_DEFAULTS = {"cell": .012, "backing": .3, "gain": 1.4}
RASTER_DEFAULTS = {"dot": .009, "gap": .2}


def fill_of(look):
    """The look's glyph fill when it is on (looks.ts fillOf)."""
    f = (look or {}).get("fill")
    return f if f and f.get("region") else None


def raster_of(look):
    """The look's raster when it is on (looks.ts rasterOf)."""
    r = (look or {}).get("raster")
    return r if r and r.get("shape") else None


def merge_overrides(cur, patch):
    out = dict(cur or {})
    for k, v in patch.items():
        out[k] = {**out[k], **v} if k in _DEEP and isinstance(out.get(k), dict) and isinstance(v, dict) else v
    return out


def resolve_look(ref):
    """{"id", "overrides"} -> full Look dict (preset + overrides), like looks.ts lookOf. None for no look."""
    if not ref or ref.get("id") in (None, "default"):
        return None
    entry = presets()["looks"].get(ref["id"])
    if not entry:
        raise ValueError(f"unknown look {ref['id']!r}; one of {LOOK_IDS()}")
    base, o = entry["look"], ref.get("overrides") or {}
    font = {**base["font"], **(o.get("font") or {})}
    for role in ("hero", "body"):
        if (o.get("font") or {}).get(role) not in (None, base["font"][role]) and f"{role}Weight" not in (o.get("font") or {}):
            font.pop(f"{role}Weight", None)
    fill = None if ("fill" in o and o["fill"] is None) else {**(base.get("fill") or {}), **o["fill"]} if o.get("fill") else base.get("fill")
    raster = None if ("raster" in o and o["raster"] is None) else {**(base.get("raster") or {}), **o["raster"]} if o.get("raster") else base.get("raster")
    return {**base, **o, "id": base["id"], "font": font, "palette": {**base["palette"], **(o.get("palette") or {})},
            "optics": {**base.get("optics", {}), **(o.get("optics") or {})}, "fill": fill, "raster": raster}


def look_param_patch(look, key, v):
    """Overrides patch for one param (looks.ts lookParamPatch)."""
    if key == "boxes": return {"noteBlocks": bool(v)}
    if key == "note": return {"palette": {"note": v}}
    if key == "noteGlow": return {"noteGlow": float(v)}
    if key == "ink": return {"palette": {"text": v}}
    if key == "accent": return {"palette": {"accent": v}}
    if key == "card": return {"palette": {"card": v}} if fill_of(look) else {"palette": {"card": v}, "card": True}
    if key == "cards": return {"card": True, "palette": {"card": "#2f6bff"}} if v and not look["palette"].get("card") else {"card": bool(v)}
    if key == "font": return {"font": {"hero": v}}
    if key == "body": return {"font": {"body": v}}
    if key == "case": return {"font": {"heroCase": v, "bodyCase": v}}
    if key == "layout": return {"layout": v}
    if key == "scale": return {"scale": float(v)}
    if key == "motion": return {"intensity": float(v)}
    if key == "glow": return {"optics": {"glow": float(v)}}
    if key == "outline": return {"outlineWidth": float(v)}
    if key == "halo": return {"halo": float(v)}
    if key == "soft": return {"optics": {"blur": float(v)}}
    if key == "scroll": return {"motion": "marquee" if v else "none"}
    if key == "hooks": return {"fill": {**look["fill"], "hooks": bool(v)}} if fill_of(look) else {"quiet": "hooks-only" if v else "none"}
    if key == "flicker": return {"flicker": float(v)}
    if key == "drips": return {"drips": float(v)}
    if key == "light": return {"light": float(v)}
    if key == "tubes": return {"finish": "neon"} if v else {"finish": None}
    # v4.3 glyph fill (any look)
    if key == "fill": return {"fill": None} if v in (None, "", "off") else {"fill": {**(look.get("fill") or {}), "region": v}}
    if key == "cell": return {"fill": {"region": "subject", **(look.get("fill") or {}), "cell": float(v)}}
    if key == "backing": return {"fill": {"region": "subject", **(look.get("fill") or {}), "backing": float(v)}}
    # v4.4 raster (any look)
    if key == "dots": return {"raster": None} if v in (None, "", "off") else {"raster": {**(look.get("raster") or {}), "shape": v}}
    if key == "dot": return {"raster": {"shape": "square", **(look.get("raster") or {}), "dot": float(v)}}
    if key == "gap": return {"raster": {"shape": "square", **(look.get("raster") or {}), "gap": float(v)}}
    if key == "pad": return {"cardPad": float(v)}
    if key == "cardGap": return {"cardGap": float(v)}
    raise KeyError(key)


def build_look(preset, params):
    """preset id + {param: value} (None = keep the preset's) -> look ref {"id", "overrides"}."""
    ref = {"id": preset, "overrides": None}
    for key in PARAMS:
        v = params.get(key)
        if v is None:
            continue
        ref["overrides"] = merge_overrides(ref["overrides"], look_param_patch(resolve_look(ref), key, v))
    return ref


def _hex(c, default=(255, 255, 255)):
    """#rrggbb or #rrggbbaa -> (r, g, b). The alpha byte is accepted and dropped: this draft draws opaque."""
    c = (c or "").lstrip("#")
    if len(c) not in (6, 8):
        return default
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def load_font(family, px, weight=None, italic=False):
    files = FONT_FILES.get(family) or FONT_FILES["Inter"]
    font = ImageFont.truetype(os.path.join(FONT_DIR, files.get("italic" if italic else "normal", files["normal"])), max(1, int(px)))
    w = weight or DEFAULT_WEIGHT.get(family)
    if w:
        try:
            axes = font.get_variation_axes()
            font.set_variation_by_axes([w if a.get("name", b"") in (b"Weight", "Weight") else a["default"] for a in axes])
        except Exception:
            pass  # static face
    return font


def apply_case(text, c):
    if c == "title":
        return re.sub(r"(^|[\s\-'\u2019])(\w)", lambda m: m.group(1) + m.group(2).upper(), text.lower())
    return text.upper() if c == "upper" else text.lower() if c == "lower" else text


def draw_look_text(base, text, look, size=None, xy=(0.5, 0.5)):
    """Draw `text` over a PIL RGB image in the look's hero style (face, case, ink, card, outline, halo, glow)."""
    w, h = base.size
    f = look["font"]
    px = int((size or 0.2 * (look.get("scale") or 1)) * h)
    font = load_font(f["hero"], px, f.get("heroWeight"), f.get("heroStyle") == "italic")
    text = apply_case(text, f.get("heroCase"))
    pal = look["palette"]
    ink = _hex(pal["accent"] if look.get("heroFill") == "accent" else pal["text"])
    probe = ImageDraw.Draw(base)
    bbox = probe.textbbox((0, 0), text, font=font, anchor="mm")
    tw = bbox[2] - bbox[0]
    if tw > w * .88:  # fit
        font = load_font(f["hero"], px * w * .88 / tw, f.get("heroWeight"), f.get("heroStyle") == "italic")
    cx, cy = xy[0] * w, xy[1] * h
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((cx, cy), text, font=font, fill=255, anchor="mm")
    out = base.convert("RGB")
    if look.get("card") and pal.get("card"):
        bb = mask.getbbox()
        if bb:
            pad = px * .32
            ImageDraw.Draw(out).rectangle((bb[0] - pad, bb[1] - pad * .75, bb[2] + pad, bb[3] + pad * .75), fill=_hex(pal["card"]))
    halo = look.get("halo") or (1.0 if look.get("texture") == "paper" else 0)
    if halo and pal.get("shadow"):
        if look.get("texture") == "paper":
            sh = Image.new("L", (w, h), 0); sh.paste(mask, (int(px * .035), int(px * .045)))
        else:
            sh = mask.filter(ImageFilter.GaussianBlur(px * .12))
        out = Image.composite(Image.new("RGB", (w, h), _hex(pal["shadow"])), out, sh.point(lambda v: int(v * min(1, halo))))
    glow = (look.get("optics") or {}).get("glow") or 0
    if look.get("finish") == "neon":
        glow = max(glow, .8)
    if glow:
        g = mask.filter(ImageFilter.GaussianBlur(glow * .03 * h)).point(lambda v: int(min(255, v * (.55 + .5 * glow))))
        out = Image.composite(Image.new("RGB", (w, h), ink), out, g)
    ow = look.get("outlineWidth") or 0
    oc = pal.get("outline") or (pal.get("shadow") or "#000000" if ow else None)
    if ow and oc:
        k = max(3, int(ow * px) * 2 + 1)
        out = Image.composite(Image.new("RGB", (w, h), _hex(oc)), out, mask.filter(ImageFilter.MaxFilter(k if k % 2 else k + 1)))
    return Image.composite(Image.new("RGB", (w, h), ink), out, mask), mask


# ---------------------------------------------------------------- grade (mirror of looks.ts gradeOf + renderer paintVideo)
def resolve_grade(ref):
    """{"id", "amount", "overrides"} -> grade dict with amount applied (monoMix = mono cross-fade), or None."""
    if not ref or (ref.get("id") == "none" and not ref.get("overrides")):
        return None
    g = {**presets()["grades"].get(ref["id"], {"grade": {}})["grade"], **(ref.get("overrides") or {})}
    a = max(0.0, min(1.0, 1.0 if ref.get("amount") is None else float(ref["amount"])))
    if a <= 0:
        return None
    if a < 1:
        g = {**g, "tint": {**g["tint"], "amount": g["tint"]["amount"] * a} if g.get("tint") else None,
             "flash": {**g["flash"], "amount": g["flash"]["amount"] * a} if g.get("flash") else None,
             "grain": (g.get("grain") or 0) * a, "halation": (g.get("halation") or 0) * a}
    return {**g, "monoMix": a}


def _lum(x):
    return x[..., 0] * .3 + x[..., 1] * .59 + x[..., 2] * .11


def _set_lum(c, l):
    """W3C compositing SetLum + ClipColor (the canvas 'color' blend)."""
    d = l - _lum(c)
    c = c + d[..., None]
    L = _lum(c)[..., None]
    n, x = c.min(-1, keepdims=True), c.max(-1, keepdims=True)
    c = np.where(n < 0, L + (c - L) * L / np.maximum(L - n, 1e-6), c)
    c = np.where(x > 1, L + (c - L) * (1 - L) / np.maximum(x - L, 1e-6), c)
    return c


def flash_at(beats, t, f):
    last = max((b for b in beats.get("beats", []) if b <= t + 1e-6), default=None)
    if last is None:
        return 0.0
    dt = t - last
    if dt > f["decay"] * 1.5:
        return 0.0
    downs = beats.get("downbeats")
    down = True if downs is None else any(abs(d - last) < .03 for d in downs)
    return f["amount"] * (1 if down else f.get("beat", .35)) * float(np.exp(-3 * dt / max(.01, f["decay"])))


def _mono_lut(m, flash):
    x = np.arange(256) / 255.0
    crush, piv = m.get("crush") or 0, .38
    x = np.minimum(1, x + flash * (.18 + .82 * x))
    x = np.maximum(0, (x - crush) / (1 - crush))
    y = np.clip(piv + (x - piv) * m["contrast"], 0, 1)
    y = .5 * y + .5 * y * y * (3 - 2 * y)
    return np.round(y * 255).astype(np.uint8)


def _mono(img8, m, flash):
    lut = _mono_lut(m, flash)
    r, g, b = (img8[..., i].astype(np.int32) for i in range(3))
    L = lut[(77 * r + 150 * g + 29 * b) >> 8].astype(np.float32)
    out = np.repeat(L[..., None], 3, -1)
    k = m.get("keep")
    if k:
        mx, mn = img8.max(-1).astype(np.float32), img8.min(-1).astype(np.float32)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
        hsv = np.asarray(Image.fromarray(img8).convert("HSV")).astype(np.float32)
        hue = hsv[..., 0] / 255 * 360
        dh = np.abs(hue - k["hue"]) % 360
        dh = np.where(dh > 180, 360 - dh, dh)
        wgt = np.clip(1 - dh / k["width"], 0, 1) * np.clip((sat - k["minSat"]) / .15, 0, 1) * (sat >= k["minSat"]) * (mx > 40)
        keep = lut[img8].astype(np.float32)
        out = L[..., None] + (keep - L[..., None]) * wgt[..., None]
    return out / 255.0


def grade_frames(frames, grade, fps=24.0, beats=None, seed=0):
    """frames: float32 [N,H,W,3] 0..1 -> graded copy. grade: resolve_grade() output."""
    if not grade:
        return frames.copy()
    out = np.empty_like(frames)
    tint = grade.get("tint")
    for i, f in enumerate(frames):
        x = f.astype(np.float32)
        if tint and tint.get("amount"):
            tc = np.array(_hex(tint["color"]), np.float32) / 255
            a1 = min(1.0, tint["amount"] * 1.6)
            x = x * (1 - a1) + _set_lum(np.broadcast_to(tc, x.shape), _lum(x)) * a1
            a2 = tint["amount"] * .5
            x = x * (1 - a2) + x * tc * a2
        hal = grade.get("halation") or 0
        if hal:
            h = x.shape[0]
            g = np.clip((_lum(x) * .55 - .5) * 4 + .5, 0, 1)
            g = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(h * .012))).astype(np.float32) / 255
            glow = g[..., None] * np.array([1, .416, .239], np.float32)
            x = x * (1 - hal) + (1 - (1 - x) * (1 - glow)) * hal
        m = grade.get("mono")
        if m:
            fl = flash_at(beats, i / fps, grade["flash"]) if grade.get("flash") and beats else 0.0
            mono = _mono((np.clip(x, 0, 1) * 255 + .5).astype(np.uint8), m, fl)
            mix = grade.get("monoMix", 1)
            x = mono if mix >= 1 else x * (1 - mix) + mono * mix
        grain = grade.get("grain") or 0
        if grain:
            rng = np.random.default_rng(seed * 100003 + i)
            n = .5 + (rng.random(x.shape[:2], np.float32) - .5) * .9
            n = n[..., None]
            ov = np.where(x < .5, 2 * x * n, 1 - 2 * (1 - x) * (1 - n))
            a = min(1.0, grain * .6)
            x = x * (1 - a) + ov * a
        out[i] = np.clip(x, 0, 1)
    return out


# ---------------------------------------------------------------- nodes
_TRI = ["preset", "on", "off"]
_tri = lambda v: None if v == "preset" else v == "on"  # noqa: E731
_neg = lambda v: None if v is None or v < 0 else float(v)  # noqa: E731


class TypesetLook:
    @classmethod
    def INPUT_TYPES(cls):
        f = lambda d, lo, hi, st, tip: ("FLOAT", {"default": d, "min": lo, "max": hi, "step": st, "tooltip": tip})  # noqa: E731
        return {"required": {
            "preset": (["default"] + LOOK_IDS(), {"default": "flat-card", "tooltip": "default = no look (look_json is empty; downstream nodes keep their own styling)"}),
            "ink": ("STRING", {"default": "", "tooltip": "Text colour #rrggbb; empty = preset"}),
            "accent": ("STRING", {"default": "", "tooltip": "Accent colour #rrggbb; empty = preset"}),
            "card": ("STRING", {"default": "", "tooltip": "Card colour #rrggbb or #rrggbbaa (turns cards on); empty = preset"}),
            "font": (["preset"] + FAMILIES, {"default": "preset"}),
            "body": (["preset"] + FAMILIES, {"default": "preset"}),
            "case": (["preset", "upper", "lower", "as-is"], {"default": "preset"}),
            "layout": (["preset", "line", "hero", "stack", "constellation", "hud"], {"default": "preset"}),
            "scale": f(1.0, .4, 2.0, .05, "Type size multiplier"),
            "motion": f(1.0, 0.0, 2.0, .05, "Entrance motion amount"),
            "glow": f(-1.0, -1.0, 1.0, .05, "-1 = preset"),
            "flicker": f(-1.0, -1.0, 1.0, .05, "Pop-in flicker; -1 = preset"),
            "drips": f(-1.0, -1.0, 1.0, .05, "Spray drips (graffiti); -1 = preset"),
            "light": f(-1.0, -1.0, 1.0, .05, "Neon light on the scene (spill, reflection, subject rim); -1 = preset"),
            "outline": f(-1.0, -1.0, .15, .005, "-1 = preset"),
            "halo": f(-1.0, -1.0, 1.0, .05, "-1 = preset"),
            "soft": f(-1.0, -1.0, 1.0, .05, "Text blur; -1 = preset"),
            "cards": (_TRI, {"default": "preset"}),
            "tubes": (_TRI, {"default": "preset", "tooltip": "Neon tubes for all text"}),
            "scroll": (_TRI, {"default": "preset", "tooltip": "LED marquee"}),
            "hooks": (_TRI, {"default": "preset", "tooltip": "Only hook lines speak (under a glyph fill: only hook lines fill)"}),
            "fill": (["preset", "off", "subject", "world", "frame"], {"default": "preset", "tooltip": "Glyph fill: filled lines become a letter grid lit by the footage (subject = inside the matte, world = around it, frame = everything; wall lines fill their wall)"}),
            "cell": f(-1.0, -1.0, .03, .001, "Glyph cell width, fraction of min(w,h); -1 = preset"),
            "backing": f(-1.0, -1.0, 1.0, .05, "Card opacity under the glyphs; -1 = preset"),
            "dots": (["preset", "off", "square", "round"], {"default": "preset", "tooltip": "Raster: the type becomes a fixed grid of dots (square = stitched pixels, round = LEDs)"}),
            "dot": f(-1.0, -1.0, .02, .001, "Dot cell size, fraction of min(w,h); -1 = preset"),
            "gap": f(-1.0, -1.0, .6, .05, "Empty fraction of each cell between dots; -1 = preset"),
        }, "optional": {"sample": ("STRING", {"default": "hold on"}),
            "note": ("STRING", {"default": "", "tooltip": "Note box colour #rrggbb or #rrggbbaa (alpha = box opacity); empty = preset"}),
            "noteGlow": f(-1.0, -1.0, 1.0, .05, "White note-box onset glow; 0 = off, -1 = preset"),
            "pad": f(-1.0, -1.0, 3.0, .05, "Card padding around the text, x the look's own; -1 = preset"),
            "cardGap": f(-1.0, -1.0, 1.0, .02, "Space between the cards of a wrapped line, x text size (0 = one block); -1 = preset"),
            "boxes": (["preset", "on", "off"], {"default": "preset", "tooltip": "Note blocks behind noted words; off hides them (the pitch stagger stays)"})}}

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("look_json", "preview")
    FUNCTION = "run"
    CATEGORY = "Reprise/look"

    def run(self, preset, ink="", accent="", card="", font="preset", body="preset", case="preset", layout="preset",
            scale=1.0, motion=1.0, glow=-1.0, outline=-1.0, halo=-1.0, soft=-1.0, cards="preset", scroll="preset",
            hooks="preset", sample="hold on", flicker=-1.0, tubes="preset", drips=-1.0, light=-1.0, fill="preset", cell=-1.0, backing=-1.0,
            dots="preset", dot=-1.0, gap=-1.0, note="", noteGlow=-1.0, boxes="preset", pad=-1.0, cardGap=-1.0):
        import torch
        if preset == "default":
            return ("", torch.zeros(1, 432, 768, 3))
        params = {"boxes": _tri(boxes), "note": note or None, "noteGlow": _neg(noteGlow), "ink": ink or None, "accent": accent or None, "card": card or None,
                  "font": None if font == "preset" else font, "body": None if body == "preset" else body,
                  "case": None if case == "preset" else case, "layout": None if layout == "preset" else layout,
                  "scale": None if scale == 1.0 else scale, "motion": None if motion == 1.0 else motion,
                  "glow": _neg(glow), "flicker": _neg(flicker), "drips": _neg(drips), "light": _neg(light), "tubes": _tri(tubes), "outline": _neg(outline), "halo": _neg(halo), "soft": _neg(soft),
                  "cards": _tri(cards), "scroll": _tri(scroll), "hooks": _tri(hooks),
                  "fill": None if fill == "preset" else fill, "cell": _neg(cell), "backing": _neg(backing),
                  "dots": None if dots == "preset" else dots, "dot": _neg(dot), "gap": _neg(gap), "pad": _neg(pad), "cardGap": _neg(cardGap)}
        ref = build_look(preset, params)
        bg = Image.new("RGB", (768, 432), (38, 41, 35))
        img, _ = draw_look_text(bg, sample or "hold on", resolve_look(ref))
        return (json.dumps(ref), torch.from_numpy(np.asarray(img, np.float32) / 255)[None])


class TypesetGrade:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "grade": (GRADE_IDS(), {"default": "film"}),
            "amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": .05}),
            "tint": ("STRING", {"default": "", "tooltip": "Tint colour #rrggbb; empty = preset"}),
            "tint_amount": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": .01, "tooltip": "-1 = preset"}),
            "grain": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": .01, "tooltip": "-1 = preset"}),
            "halation": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": .01, "tooltip": "-1 = preset"}),
            "contrast": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 3.0, "step": .05, "tooltip": "Mono contrast (turns mono on); -1 = preset"}),
            "flash": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": .05, "tooltip": "Beat flash amount (needs beats_json and mono); -1 = preset"}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": .001}),
        }, "optional": {"beats_json": ("STRING", {"default": "", "forceInput": True}), "seed": ("INT", {"default": 0, "min": 0, "max": 2**31 - 1})}}

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "grade_json")
    FUNCTION = "run"
    CATEGORY = "Reprise/look"

    @staticmethod
    def ref(grade, amount=1.0, tint="", tint_amount=-1.0, grain=-1.0, halation=-1.0, contrast=-1.0, flash=-1.0):
        base = presets()["grades"][grade]["grade"]
        o = {}
        if tint or tint_amount >= 0:
            t = base.get("tint") or {"color": "#808080", "amount": .3}
            o["tint"] = {"color": tint or t["color"], "amount": t["amount"] if tint_amount < 0 else tint_amount}
        if grain >= 0: o["grain"] = grain
        if halation >= 0: o["halation"] = halation
        if contrast >= 0: o["mono"] = {**(base.get("mono") or {"crush": .02}), "contrast": contrast}
        if flash >= 0: o["flash"] = {**(base.get("flash") or {"decay": .2, "beat": .35}), "amount": flash}
        return {"id": grade, "amount": amount, "overrides": o or None}

    def run(self, images, grade, amount, tint="", tint_amount=-1.0, grain=-1.0, halation=-1.0, contrast=-1.0,
            flash=-1.0, fps=24.0, beats_json="", seed=0):
        import torch
        ref = self.ref(grade, amount, tint, tint_amount, grain, halation, contrast, flash)
        beats = json.loads(beats_json) if beats_json else None
        out = grade_frames(images.detach().cpu().numpy()[..., :3].astype(np.float32), resolve_grade(ref), fps, beats, seed)
        return (torch.from_numpy(out), json.dumps(ref))


class TypesetGradeSettings:
    """Grade configuration for a downstream renderer, without grading an unused IMAGE batch."""
    @classmethod
    def INPUT_TYPES(cls):
        required = TypesetGrade.INPUT_TYPES()["required"]
        return {"required": {k: v for k, v in required.items() if k not in ("images", "fps")}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("grade_json",)
    FUNCTION = "run"
    CATEGORY = "Reprise/look"

    def run(self, grade, amount=1.0, tint="", tint_amount=-1.0, grain=-1.0, halation=-1.0, contrast=-1.0, flash=-1.0):
        return (json.dumps(TypesetGrade.ref(grade, amount, tint, tint_amount, grain, halation, contrast, flash)),)


NODE_CLASS_MAPPINGS = {"TypesetLook": TypesetLook, "TypesetGrade": TypesetGrade, "TypesetGradeSettings": TypesetGradeSettings}
NODE_DISPLAY_NAME_MAPPINGS = {"TypesetLook": "Look • text style (Reprise)", "TypesetGrade": "Grade • footage (Reprise)",
                              "TypesetGradeSettings": "Grade settings • footage (Reprise)"}
