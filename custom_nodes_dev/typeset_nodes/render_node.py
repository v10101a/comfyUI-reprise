"""TypesetRender: words + look (+ subject matte, voice and motion fields) burned into an IMAGE batch, in the graph.

Two renderers, picked by the `renderer` input:
  studio  the graph's inputs become a Typeset project that headless Chromium renders through the studio's own
          renderer (browser_render.py): every look (walls, neon relight, graffiti, ticker, HUD, entrances, fields),
          pixel-identical to a studio export of that project. Needs the /typeset host (studio_host.py), a built
          studio (apps/web/dist) and Playwright.
  draft   this file's Python port: one lyric line at a time, centred at `height`, words popping in on their timing,
          behind the subject when a mask is connected; font, palette and glow only. No browser needed.
  auto    studio when available, otherwise draft. The `renderer` output and the log say which one ran.

The draft's voice/flow rules follow apps/web src/voice.ts and src/flow.ts at draft fidelity.
"""
import json
import logging
import math
import time

import cv2
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFilter

from . import core_vision as cv
from .looks import _hex, apply_case, grade_frames, load_font, resolve_grade, resolve_look

log = logging.getLogger("typeset.render")

DEFAULT_LOOK = {"id": "red-glow", "overrides": None}


# ---- voice (port of apps/web/src/voice.ts) ---------------------------------------------------------

class Voice:
    def __init__(self, doc):
        self.doc = doc

    def _val(self, key, t):
        a, x = self.doc[key], (t - (self.doc.get("t0") or 0)) * self.doc["fps"]
        i, k = int(math.floor(x)), x - math.floor(x)
        a0 = a[i] if 0 <= i < len(a) else None
        a1 = a[i + 1] if 0 <= i + 1 < len(a) else None
        if a0 is None:
            return None if a1 is None or k < .5 else a1
        return a0 if a1 is None else a0 + (a1 - a0) * k

    def _smooth(self, key, t, r=4):
        s = w = 0.0
        for k in range(-r, r + 1):
            v = self._val(key, t + k / self.doc["fps"])
            if v is None:
                continue
            g = math.exp(-k * k / (2 * (r / 2) ** 2))
            s, w = s + v * g, w + g
        return s / w if w else None

    def _kick(self, t):
        fps = self.doc["fps"]
        return max(((self._val("onset", t - i / fps) or 0) * math.exp(-i / (.15 * fps)) for i in range(8)), default=0)

    def _level(self, t):
        """TypesetAudioField doc (kind 'bass'): frame value held for the whole frame, release-only smoothing over the
        last 3 frames (0.25 s), as voice.ts AudioField: rises at once on the kick, never before it."""
        a, fps = self.doc["level"], self.doc["fps"]

        def v(tt):
            i = int(math.floor((tt - (self.doc.get("t0") or 0)) * fps + 1e-6))
            return a[i] if 0 <= i < len(a) else 0
        d, r = 1 / fps, math.exp(-1 / (fps * .25))
        return max(v(t - k * d) * r ** k for k in range(4))

    def ref_pitch(self, t0, t1):
        if self.doc.get("kind") == "bass":
            return None
        o = self.doc.get("t0") or 0
        f0, f1 = max(0, int((t0 - o) * self.doc["fps"])), min(self.doc["frames"], int(math.ceil((t1 - o) * self.doc["fps"])))
        ps = sorted(p for p in self.doc["pitch"][f0:f1] if p is not None)
        return ps[len(ps) // 2] if ps else None

    def mods(self, t, start, end, ref, amount):
        """-> (weight delta, sx, sy, dy in units of size); identity when amount is 0 or before the word."""
        if amount <= 0 or t < start:
            return 0.0, 1.0, 1.0, 0.0
        tt, hold = min(t, end), (math.exp(-(t - end) / .4) if t > end else 1.0)
        if self.doc.get("kind") == "bass":  # the mix's low band: size pulse only
            s = 1 + amount * .24 * self._level(tt) * hold
            return 0.0, s, s, 0.0
        loud = (self._smooth("loud", tt) or 0) * hold
        p = self._smooth("pitch", tt)
        vib = (self._smooth("vibrato", tt) or 0) * hold
        on = self._kick(tt) * hold
        # Size only (as in voice.ts): loudness swells weight + scale, attacks pulse; no baseline motion.
        grow = .14 * (loud - .45) + .07 * on
        return amount * 500 * (loud - .45), 1 + amount * grow, 1 + amount * grow, 0.0


# ---- motion (port of apps/web/src/flow.ts) ----------------------------------------------------------
# Camera motion (the frame's median flow) carries the type with inertia; motion against the camera (a dancer's
# arm, a spin) pushes it like liquid with a short trail. Both are smoothed over ±2 frames so the type glides.


class Flow:
    def __init__(self, doc):
        self.doc, self.raw, self.loc, self.sm = doc, {}, {}, {}

    def _decode(self, f):
        if f < 0 or f >= len(self.doc["frames"]):
            return None
        if f not in self.raw:
            g = cv.decode_flow(self.doc["frames"][f], self.doc["cols"], self.doc["rows"], self.doc["scale"])
            self.raw[f] = (g, float(np.median(g[..., 0])), float(np.median(g[..., 1])))
        return self.raw[f]

    def camera(self, f):
        rs = [r for r in (self._decode(f + k) for k in range(-2, 3)) if r]
        return (sum(r[1] for r in rs) / len(rs), sum(r[2] for r in rs) / len(rs)) if rs else (0.0, 0.0)

    def drift(self, f, span=16, decay=.86):
        x = y = 0.0
        w = 1.0
        for i in range(span):
            a, b = self.camera(f - i)
            x, y, w = x + a * w, y + b * w, w * decay
        return x, y

    def _local(self, f):
        if f not in self.loc:
            r = self._decode(f)
            if r is None:
                return None
            g = r[0] - np.array([r[1], r[2]], np.float32)
            for _ in range(2):
                g = cv2.blur(g, (7, 7), borderType=cv2.BORDER_REPLICATE)
            self.loc[f] = g
        return self.loc[f]

    def grid(self, f):
        if f not in self.sm:
            acc, w = None, 0.0
            for k in range(-2, 3):
                l = self._local(f + k)
                if l is None:
                    continue
                g = math.exp(-k * k / 2)
                acc = l * g if acc is None else acc + l * g
                w += g
            self.sm[f] = None if acc is None else acc / w
        return self.sm[f]

    def push(self, f, span=14, decay=.84):
        acc, w = None, 1.0
        for i in range(span):
            g = self.grid(f - i)
            if g is not None:
                acc = g * w if acc is None else acc + g * w
            w *= decay
        return acc


def warp_motion(layer, flow, f, amount):
    """layer: HxWx4 float RGBA (premultiplied): camera drift + liquid push + a short soft trail."""
    H, W = layer.shape[:2]
    capd, capp = .06 * min(W, H), .05 * H * max(.3, amount)
    cx, cy = flow.drift(f)
    ddx, ddy = float(capd * np.tanh(cx * W * 1.5 * amount / capd)), float(capd * np.tanh(cy * H * 1.5 * amount / capd))
    push, vel = flow.push(f), flow.grid(f)
    xs, ys = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    if push is None or vel is None:
        return cv2.remap(layer, xs - ddx, ys - ddy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    softp = lambda d: capp * np.tanh(d / capp)  # noqa: E731
    up = lambda g, c, s: cv2.resize(np.ascontiguousarray(g[..., c]), (W, H), interpolation=cv2.INTER_CUBIC) * s  # noqa: E731
    px, py = softp(up(push, 0, W * 2.2 * amount)) + ddx, softp(up(push, 1, H * 2.2 * amount)) + ddy
    vx, vy = softp(up(vel, 0, W * 3 * amount)), softp(up(vel, 1, H * 3 * amount))
    out = np.zeros_like(layer)
    K = 4
    for k in range(K, -1, -1):  # trail first, faintest; the pushed type last
        mx, my = (xs - px + vx * k / K).astype(np.float32), (ys - py + vy * k / K).astype(np.float32)
        copy = cv2.remap(layer, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        a = 1.0 if k == 0 else .3 * (1 - k / (K + 1)) * min(1, amount * 1.5)
        out = copy * a + out * (1 - copy[..., 3:4] * a)
    return out


# ---- layout ----------------------------------------------------------------------------------------

def parse_lines(words_json):
    doc = json.loads(words_json) if isinstance(words_json, str) else words_json
    words = doc["words"] if isinstance(doc, dict) else doc
    lines, order = {}, []
    for w in words:
        if w.get("hidden") or not str(w.get("text", "")).strip():
            continue
        lid = w.get("lineId") or "l0"
        if lid not in lines:
            lines[lid] = []
            order.append(lid)
        lines[lid].append(w)
    out = []
    for lid in order:
        ws = sorted(lines[lid], key=lambda w: w["start"])
        out.append({"id": lid, "words": ws, "start": ws[0]["start"], "end": ws[-1]["end"]})
    # A line stays up until the next one starts (max 1.2 s of hold).
    for a, b in zip(out, out[1:] + [None]):
        a["until"] = min(a["end"] + 1.2, b["start"]) if b else a["end"] + 1.2
    return out


def draw_line(W, H, line, t, look, size, y, voice, voice_amount):
    """RGBA float layer (premultiplied) with the line's sung words at time t."""
    f = look["font"]
    pal = look["palette"]
    ink = _hex(pal.get("text"), (255, 255, 255))
    accent = _hex(pal.get("accent"), ink)
    base_w = f.get("heroWeight") or 700
    px = size * H * (look.get("scale") or 1)
    ref = voice.ref_pitch(line["start"], line["end"]) if voice else None
    items = []
    for w in line["words"]:
        if t < w["start"]:
            continue
        text = apply_case(w["text"], f.get("heroCase"))
        dw, sx, sy, dy = voice.mods(t, w["start"], w["end"], ref, voice_amount) if voice else (0, 1, 1, 0)
        pop = min(1.0, (t - w["start"]) / .12)
        font = load_font(f["hero"], px * sy * (.85 + .15 * pop), int(max(100, min(900, base_w + dw))), f.get("heroStyle") == "italic")
        l, top, r, b = font.getbbox(text)
        items.append((text, font, r - l, sx, dy * px, t < w["end"], -l, -top, b - top))
    if not items:
        return None
    gap = px * .28
    total = sum(it[2] * it[3] for it in items) + gap * (len(items) - 1)
    # Short lines grow to fill the frame (up to 2.4× the set size), long ones shrink to fit.
    scale = min(2.4, W * .84 / max(total, 1))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = (W - total * scale) / 2
    for text, font, tw, sx, dy, active, ox, oy, th in items:
        tile = Image.new("RGBA", (max(1, int(tw + 4)), max(1, int(th + 4))), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((ox + 2, oy + 2), text, font=font, fill=(*(accent if active and look.get("heroFill") == "accent" else ink), 255))
        tw2, th2 = max(1, int(tile.width * sx * scale)), max(1, int(tile.height * scale))
        tile = tile.resize((tw2, th2), Image.LANCZOS)
        img.alpha_composite(tile, (int(x), int(y * H - th2 / 2 + dy * scale)))
        x += (tw * sx + gap) * scale
    glow = (look.get("optics") or {}).get("glow") or 0
    if glow > 0:
        halo = img.filter(ImageFilter.GaussianBlur(glow * .03 * H))
        img = Image.alpha_composite(Image.fromarray((np.asarray(halo).astype(np.float32) * [1, 1, 1, min(1, .55 + .5 * glow)]).astype(np.uint8)), img)
    a = np.asarray(img).astype(np.float32) / 255
    a[..., :3] *= a[..., 3:4]
    return a


def _linked(prompt, unique_id, output=None, input_name=None):
    """From the hidden PROMPT: is this node's `output` index used downstream / is `input_name` connected?"""
    if not isinstance(prompt, dict) or unique_id is None:
        return None
    uid = str(unique_id)
    if input_name is not None:
        return isinstance(((prompt.get(uid) or {}).get("inputs") or {}).get(input_name), list)
    return any(isinstance(v, list) and len(v) == 2 and str(v[0]) == uid and v[1] == output
               for node in prompt.values() for v in (node.get("inputs") or {}).values())


class TypesetRender:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "words_json": ("STRING", {"forceInput": True, "tooltip": "words.json from Align Lyrics / Whisper Words."}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001}),
        }, "optional": {
            "look_json": ("STRING", {"forceInput": True, "tooltip": "From the Look node ({id, overrides}). Not connected: red-glow."}),
            "subject_mask": ("MASK", {"tooltip": "Subject matte: the words go behind the person."}),
            "voice_json": ("STRING", {"forceInput": True, "tooltip": "From the Voice Field node."}),
            "flow_json": ("STRING", {"forceInput": True, "tooltip": "From the Motion Field node."}),
            "voice": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "How much the voice moves the type."}),
            "flow": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Camera drift + liquid push from what moves through the type."}),
            "size": ("FLOAT", {"default": 0.16, "min": 0.03, "max": 0.5, "step": 0.01, "tooltip": "Draft renderer only: type size, fraction of frame height."}),
            "height": ("FLOAT", {"default": 0.42, "min": 0.05, "max": 0.95, "step": 0.01, "tooltip": "Draft renderer only: line centre, fraction of frame height."}),
            "grade_json": ("STRING", {"forceInput": True, "tooltip": "From the Grade node (project.grade). Connect UNgraded images: the renderer grades footage and subject, as the studio does."}),
            "renderer": (["auto", "studio", "draft"], {"default": "auto", "tooltip": "studio: the studio's renderer in headless Chromium (pixel-exact, every look). draft: Python approximation. auto: studio when available."}),
        }, "hidden": {"prompt": "PROMPT", "unique_id": "UNIQUE_ID"}}

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("images", "text_layer", "renderer")
    FUNCTION = "run"
    CATEGORY = "Reprise/render"
    DESCRIPTION = "Burn lyric type into footage with the studio's renderer: behind the subject, moved by the voice and by motion in the shot."

    def run(self, images, words_json, fps, look_json="", subject_mask=None, voice_json="", flow_json="",
            voice=1.0, flow=1.0, size=0.16, height=0.42, grade_json="", renderer="auto", prompt=None, unique_id=None):
        want_text = _linked(prompt, unique_id, output=1)
        look_linked = _linked(prompt, unique_id, input_name="look_json")
        look_ref = json.loads(look_json) if look_json else (None if look_linked else DEFAULT_LOOK)
        grade_ref = json.loads(grade_json) if grade_json else None
        reason = None
        if renderer != "draft":
            from . import browser_render as br
            reason = br.unavailable()
            if reason is None:
                try:
                    return self.studio(br, images, words_json, fps, look_ref, grade_ref, subject_mask, voice_json,
                                       flow_json, voice, flow, want_text is not False)
                except Exception as exc:  # noqa: BLE001 — fall back, and say so
                    if renderer == "studio":
                        raise
                    log.exception("TypesetRender: studio renderer failed; using the draft renderer")
                    reason = f"studio renderer failed: {type(exc).__name__}: {str(exc)[:300]}"
            elif renderer == "studio":
                raise RuntimeError(f"TypesetRender: studio renderer unavailable: {reason}")
        t0 = time.monotonic()
        if grade_ref:
            images = torch.from_numpy(grade_frames(images.detach().cpu().numpy()[..., :3].astype(np.float32),
                                                   resolve_grade(grade_ref), fps))
        out, text = self.draft(images, words_json, fps, look_ref or DEFAULT_LOOK, subject_mask, voice_json, flow_json,
                               voice, flow, size, height)
        info = f"draft (python) · {out.shape[0]} frames in {time.monotonic() - t0:.1f}s" + (f" · {reason}" if reason else "")
        log.info("TypesetRender: %s", info)
        print(f"[typeset] TypesetRender: {info}")
        return {"ui": {"text": [info]}, "result": (out, text, info)}

    def studio(self, br, images, words_json, fps, look_ref, grade_ref, subject_mask, voice_json, flow_json, voice, flow,
               want_text):
        import shutil
        t0 = time.monotonic()
        B = images.shape[0]
        fields = {}
        if flow_json:
            fields["motion"] = flow
        if voice_json:
            fields["voice"] = voice
        project = br.build_project(images, words_json, fps, look_ref, grade_ref, subject_mask, voice_json, flow_json,
                                   fields)
        t1 = time.monotonic()
        layers = ("composite", "text") if want_text else ("composite",)
        pbar = None
        try:
            import comfy.utils
            pbar = comfy.utils.ProgressBar(B * len(layers))
        except Exception:
            pass
        frames, work = br.render(project, layers, tick=(lambda: pbar.update(1)) if pbar else None)
        try:
            out = torch.from_numpy(br.load_rgb(frames["composite"]))
            text = torch.from_numpy(br.load_rgb(frames["text"], premultiply_alpha=True)) if want_text else torch.zeros_like(out[:1])
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if out.shape[1:3] != images.shape[1:3]:
            raise RuntimeError(f"studio renderer returned {tuple(out.shape[1:3])}, expected {tuple(images.shape[1:3])}")
        info = (f"studio (chromium) · project {project.id} · {B} frames · look {(look_ref or {}).get('id', 'default')}"
                f" · prepare {t1 - t0:.1f}s + render {time.monotonic() - t1:.1f}s"
                + ("" if want_text else " · text_layer not connected, skipped") + f" · {br.studio_url(project)}")
        log.info("TypesetRender: %s", info)
        print(f"[typeset] TypesetRender: {info}")
        return {"ui": {"text": [info]}, "result": (out, text, info)}

    def draft(self, images, words_json, fps, look_json, subject_mask, voice_json, flow_json, voice, flow, size, height):
        look = resolve_look(look_json) or resolve_look(DEFAULT_LOOK)
        lines = parse_lines(words_json)
        vf = Voice(json.loads(voice_json)) if voice_json and voice > 0 else None
        ff = Flow(json.loads(flow_json)) if flow_json and flow > 0 else None
        B, H, W = images.shape[:3]
        out, text_out = [], []
        pbar = None
        try:
            import comfy.utils
            pbar = comfy.utils.ProgressBar(B)
        except Exception:
            pass
        for i in range(B):
            t = i / fps
            frame = images[i, ..., :3].cpu().numpy().astype(np.float32)
            layer = np.zeros((H, W, 4), np.float32)
            for line in lines:
                if line["start"] <= t < line["until"]:
                    lay = draw_line(W, H, line, t, look, size, height, vf, voice)
                    if lay is not None:
                        layer = lay + layer * (1 - lay[..., 3:4])
            if ff is not None and layer[..., 3].any():
                layer = warp_motion(layer, ff, i, flow)
            if subject_mask is not None and i < subject_mask.shape[0]:
                m = subject_mask[i].cpu().numpy().astype(np.float32)
                if m.shape != (H, W):
                    m = cv2.resize(m, (W, H))
                layer = layer * (1 - m[..., None])
            out.append(frame * (1 - layer[..., 3:4]) + layer[..., :3])
            text_out.append(np.concatenate([layer[..., :3], layer[..., 3:4]], -1)[..., :3])
            if pbar:
                pbar.update(1)
        return (torch.from_numpy(np.stack(out)).clamp(0, 1), torch.from_numpy(np.stack(text_out)).clamp(0, 1))


NODE_CLASS_MAPPINGS = {"TypesetRender": TypesetRender}
NODE_DISPLAY_NAME_MAPPINGS = {"TypesetRender": "Reprise Render • words in the shot (Reprise)"}
