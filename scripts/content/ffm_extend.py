"""Extend the 1080x1280 Fall For Me cut to 16:9 (1920x1080) or 9:16 (1080x1920) without cropping.

  ~/ComfyUI/.venv/bin/python scripts/content/ffm_extend.py <16x9|9x16> [--frames 0,200,600] [--matte <src_matte_dir> <dst_matte_dir>]

Procedural fill (no generative model): the original frame sits in the middle, unchanged. Each pad is
  - a sky colour sampled from the frame's outer band (per-row medians for side pads, per-column for top/bottom),
    smoothed along the edge and in time (EMA) so the HUD/piano-roll bits at the edge don't flicker into it,
  - a gentle continuation of the edge's colour slope (fading toward the band mean),
  - grain matched to the footage, and a few procedural four-point twinkles like the footage's sparkles,
  - and a feathered seam: the outer 48 px of the original are cross-faded into the fill.
Writes outputs/ffm/work/ffm_v7_<aspect>.mp4 (or stills to outputs/ffm/work/ext_<aspect>_fNNN.png with --frames). With --matte,
it pads the key matte (fg_%05d.png) the same way instead.
"""
import subprocess, sys
from pathlib import Path
import cv2, numpy as np
ROOT = Path(__file__).resolve().parents[2]; WORK = ROOT / "outputs/ffm/work"; FF = "/opt/homebrew/bin/ffmpeg"
SRC = WORK / "ffm_v7_30.mp4"
GEOM = {"16x9": dict(W=1920, H=1080, w=912, h=1080, x0=504, y0=0, axis="x", pct=35, feather=64),
        "9x16": dict(W=1080, H=1920, w=1080, h=1280, x0=0, y0=320, axis="y", pct=50, feather=160)}   # 9:16: wider seam (bands were visible at 64 px)
BAND, FEATHER, EMA = 48, 64, .2
PCT, SMOOTH = 35, 90     # a low percentile ignores flashes/sparkles at the edge; heavy smoothing kills streaks
rng = np.random.default_rng(7)

def make_twinkles(g, n=14):
    """Fixed positions in the pads (deterministic), each with its own phase/period/size."""
    pts = []
    while len(pts) < n:
        x, y = rng.uniform(0, g["W"]), rng.uniform(0, g["H"])
        inside = g["x0"] - 20 < x < g["x0"] + g["w"] + 20 and g["y0"] - 20 < y < g["y0"] + g["h"] + 20
        if not inside: pts.append((x, y, rng.uniform(0, 6.28), rng.uniform(1.6, 3.4), rng.uniform(10, 26)))
    return pts

def draw_twinkle(img, x, y, a, r):
    if a <= .02: return
    ov = np.zeros_like(img); c = (255, 255, 255); ix, iy = int(x), int(y)
    pts = np.array([[ix, iy - r], [ix + r * .16, iy - r * .16], [ix + r, iy], [ix + r * .16, iy + r * .16],
                    [ix, iy + r], [ix - r * .16, iy + r * .16], [ix - r, iy], [ix - r * .16, iy - r * .16]], np.int32)
    cv2.fillPoly(ov, [pts], c, cv2.LINE_AA)
    glow = cv2.GaussianBlur(ov, (0, 0), r * .45)
    img[:] = np.clip(img + (ov * .85 + glow * .9) * a / 255. * 255, 0, 255)

class Extender:
    def __init__(self, aspect):
        self.g = GEOM[aspect]; self.prev = None; self.tw = make_twinkles(self.g)
        ramp = np.linspace(0, 1, self.g['feather'])[:, None]; self.F = self.g['feather']; self.P = self.g['pct']
        self.ramp = ramp

    def fill(self, small):
        g = self.g; f = small.astype(np.float32)
        if g["axis"] == "x":   # side pads: per-row colour of the left/right bands
            L = np.percentile(f[:, :BAND], self.P, 1); R = np.percentile(f[:, -BAND:], self.P, 1)
            L2 = np.percentile(f[:, BAND:3 * BAND], self.P, 1); R2 = np.percentile(f[:, -3 * BAND:-BAND], self.P, 1)
            prof = np.stack([L, R, L - L2, R - R2]).astype(np.float32)    # (4, h, 3)
        else:                  # top/bottom pads: per-column colour
            T = np.percentile(f[:BAND], self.P, 0); B = np.percentile(f[-BAND:], self.P, 0)
            T2 = np.percentile(f[BAND:3 * BAND], self.P, 0); B2 = np.percentile(f[-3 * BAND:-BAND], self.P, 0)
            prof = np.stack([T, B, T - T2, B - B2]).astype(np.float32)    # (4, w, 3)
        # smooth along the edge only (an image of 4 rows x n cols x 3 channels; ksize height 1 = no mixing between profiles)
        prof = cv2.GaussianBlur(prof, (0, 1), sigmaX=SMOOTH, borderType=cv2.BORDER_REFLECT)
        self.prev = prof if self.prev is None else self.prev * (1 - EMA) + prof * EMA
        return self.prev

    def frame(self, img, t):
        g = self.g; small = cv2.resize(img, (g["w"], g["h"]), interpolation=cv2.INTER_AREA)
        e0, e1, s0, s1 = self.fill(small)
        out = np.zeros((g["H"], g["W"], 3), np.float32)
        if g["axis"] == "x":
            for side, edge, slope in (("L", e0, s0), ("R", e1, s1)):
                n = g["x0"]; d = np.arange(n, 0, -1) if side == "L" else np.arange(1, n + 1)   # distance from the frame edge
                k = (np.minimum(d, 400) / (2 * BAND))[None, :, None] * .35 * np.exp(-d / 500)[None, :, None]
                mean = edge.mean(0, keepdims=True)[:, None, :]
                pad = edge[:, None, :] + slope[:, None, :] * k
                pad = pad + (mean - pad) * (1 - np.exp(-d / 350))[None, :, None] * .7
                if side == "L": out[:, :n] = pad
                else: out[:, g["x0"] + g["w"]:] = pad
        else:
            for side, edge, slope in (("T", e0, s0), ("B", e1, s1)):
                n = g["y0"]; d = np.arange(n, 0, -1) if side == "T" else np.arange(1, n + 1)
                k = (np.minimum(d, 400) / (2 * BAND))[:, None, None] * .35 * np.exp(-d / 500)[:, None, None]
                mean = edge.mean(0, keepdims=True)[None, :, :]
                pad = edge[None, :, :] + slope[None, :, :] * k
                pad = pad + (mean - pad) * (1 - np.exp(-d / 350))[:, None, None] * .7
                if side == "T": out[:n] = pad
                else: out[g["y0"] + g["h"]:] = pad
        # grain like the footage (std of its high-pass), only in the pads
        hp = small.astype(np.float32) - cv2.GaussianBlur(small.astype(np.float32), (0, 0), 2)
        sd = float(np.median(np.abs(hp[:, :BAND] if g["axis"] == "x" else hp[:BAND]))) * 1.4826
        out += rng.normal(0, max(sd, 1.), out.shape).astype(np.float32)
        for (x, y, ph, per, r) in self.tw:
            a = max(0., np.sin(ph + 2 * np.pi * t / per)) ** 3
            draw_twinkle(out, x, y, a * .8, r)
        # the original, with its outer FEATHER px cross-faded into the fill
        reg = out[g["y0"]:g["y0"] + g["h"], g["x0"]:g["x0"] + g["w"]]
        alpha = np.ones((g["h"], g["w"], 1), np.float32)
        if g["axis"] == "x":
            alpha[:, :self.F, 0] = np.minimum(alpha[:, :self.F, 0], self.ramp[:, 0][None, :])
            alpha[:, -self.F:, 0] = np.minimum(alpha[:, -self.F:, 0], self.ramp[::-1, 0][None, :])
        else:
            alpha[:self.F] = np.minimum(alpha[:self.F], self.ramp[:, :, None])
            alpha[-self.F:] = np.minimum(alpha[-self.F:], self.ramp[::-1, :, None])
        alpha = alpha ** .7
        # under the seam, the fill continues the edge colour rather than a hard pad
        under = np.empty_like(reg)
        if g["axis"] == "x":
            under[:] = np.linspace(0, 1, g["w"])[None, :, None] * e1[:, None, :] + (1 - np.linspace(0, 1, g["w"]))[None, :, None] * e0[:, None, :]
        else:
            under[:] = np.linspace(0, 1, g["h"])[:, None, None] * e1[None, :, :] + (1 - np.linspace(0, 1, g["h"]))[:, None, None] * e0[None, :, :]
        out[g["y0"]:g["y0"] + g["h"], g["x0"]:g["x0"] + g["w"]] = small * alpha + under * (1 - alpha)
        return np.clip(out, 0, 255).astype(np.uint8)

def frames_of(path):
    cap = cv2.VideoCapture(str(path)); i = 0
    while True:
        ok, f = cap.read()
        if not ok: return
        yield i, f; i += 1

def main():
    aspect = sys.argv[1]; g = GEOM[aspect]; args = sys.argv[2:]
    if args[:1] == ["--matte"]:
        src, dst = Path(args[1]), Path(args[2]); dst.mkdir(parents=True, exist_ok=True)
        for p in sorted(src.glob("fg_*.png")):
            m = cv2.imread(str(p), cv2.IMREAD_UNCHANGED); m = cv2.resize(m, (g["w"], g["h"]), interpolation=cv2.INTER_AREA)
            c = np.zeros((g["H"], g["W"]) + m.shape[2:], m.dtype); c[g["y0"]:g["y0"] + g["h"], g["x0"]:g["x0"] + g["w"]] = m
            cv2.imwrite(str(dst / p.name), c)
        print("matte", dst); return
    ex = Extender(aspect)
    if args[:1] == ["--frames"]:
        want = {int(x) for x in args[1].split(",")}
        for i, f in frames_of(SRC):     # run every frame so the EMA is warm, save the wanted ones
            o = ex.frame(f, i / 30)
            if i in want: cv2.imwrite(str(WORK / f"ext_{aspect}_f{i:03d}.png"), o)
            if i >= max(want): break
        return
    out = WORK / f"ffm_v7_{aspect}.mp4"
    p = subprocess.Popen([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{g['W']}x{g['H']}", "-r", "30", "-i", "-",
                          "-c:v", "libx264", "-preset", "slow", "-crf", "15", "-g", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
                         stdin=subprocess.PIPE)
    for i, f in frames_of(SRC): p.stdin.write(ex.frame(f, i / 30).tobytes())
    p.stdin.close(); p.wait(); print(out)

if __name__ == "__main__":
    main()
