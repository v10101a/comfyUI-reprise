"""Typeset core vision — pure numpy/OpenCV/Pillow logic shared by the ComfyUI nodes in this pack
and by the Typeset server's in-process fallback (server/app/vision.py loads this file; there is one copy).

  occupancy_*      MASK → coarse grid of "how much subject is in each cell" (where text stays readable)
  track_plane      planar homography tracker for a 4-corner quad on a wall/sign, subject masked out
  compute_crop     smoothed virtual camera (dead zone + critically damped follow) for reframing

No torch, no ComfyUI imports: everything here is unit-testable on synthetic data.
"""
from __future__ import annotations

import base64
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

# ---- B. occupancy ----------------------------------------------------------------------

OCC_LONG = 32  # cells along the long edge; 32×18 for 16:9, 18×32 for 9:16


def occupancy_dims(width: int, height: int, long_cells: int = OCC_LONG) -> tuple[int, int]:
    """(cols, rows) with roughly square cells."""
    if width >= height:
        return long_cells, max(1, round(long_cells * height / width))
    return max(1, round(long_cells * width / height)), long_cells


def occupancy_cells(alpha: np.ndarray, cols: int, rows: int) -> np.ndarray:
    """alpha: HxW uint8 (0..255) → rows×cols uint8, each = fraction of the cell covered (area average)."""
    from PIL import Image

    im = Image.fromarray(np.ascontiguousarray(alpha, dtype=np.uint8), mode="L")
    small = im.resize((cols, rows), Image.Resampling.BOX)
    return np.asarray(small, dtype=np.uint8)


def encode_occupancy(cells: np.ndarray) -> str:
    """Row-major, top row first, base64 of cols*rows uint8."""
    return base64.b64encode(np.ascontiguousarray(cells, dtype=np.uint8).tobytes()).decode("ascii")


def decode_occupancy(data: str, cols: int, rows: int) -> np.ndarray:
    raw = np.frombuffer(base64.b64decode(data), dtype=np.uint8)
    if raw.size != cols * rows:
        raise ValueError(f"occupancy entry has {raw.size} cells, expected {cols * rows}")
    return raw.reshape(rows, cols)


# ---- A. planar surface tracking --------------------------------------------------------

@dataclass
class TrackParams:
    max_corners: int = 600
    quality: float = 0.005
    min_distance: int = 6
    expand: float = 1.0           # also use features in the quad grown by this fraction (same plane, more texture)
    subject_thresh: int = 60      # alpha above this = subject (masked out)
    subject_dilate: int = 15      # px of extra margin around the subject
    fb_max_err: float = 1.5       # forward-backward LK error in px
    ransac_px: float = 3.0
    min_inliers: int = 12
    min_conf: float = 0.35        # frames below this are dropped (= "lost")
    replenish_below: int = 120    # detect new features when the live set falls under this
    smooth: int = 2               # ± frames of corner smoothing (triangular)
    refine: bool = True           # dense ECC refinement of every pose against the key frame (removes drift)
    ecc_scale: float = 0.5        # ECC works on images scaled by this
    ecc_min_rho: float = 0.6      # accept the refined pose only above this correlation
    ecc_min_visible: float = 0.4  # ...and only when this much of the key-frame region is in view and unoccluded
    weak_visible: float = 0.45    # below this visible fraction the full homography is ill-conditioned: update the
                                  # previous pose with a 4-DOF (similarity) motion instead


def _quad_mask(shape: tuple[int, int], quad_px: np.ndarray, expand: float = 0.0) -> np.ndarray:
    import cv2

    q = quad_px.astype(np.float64)
    if expand:
        c = q.mean(axis=0)
        q = c + (q - c) * (1 + expand)
    mask = np.zeros(shape, np.uint8)
    cv2.fillConvexPoly(mask, np.round(q).astype(np.int32), 255)
    return mask


def _subject_free(shape, subject_alpha: np.ndarray | None, p: TrackParams) -> np.ndarray:
    import cv2

    if subject_alpha is None:
        return np.full(shape, 255, np.uint8)
    sub = (subject_alpha > p.subject_thresh).astype(np.uint8) * 255
    if p.subject_dilate:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * p.subject_dilate + 1,) * 2)
        sub = cv2.dilate(sub, k)
    return cv2.bitwise_not(sub)


def _detect(gray: np.ndarray, mask: np.ndarray, p: TrackParams, n: int | None = None) -> np.ndarray:
    import cv2

    pts = cv2.goodFeaturesToTrack(gray, maxCorners=n or p.max_corners, qualityLevel=p.quality,
                                  minDistance=p.min_distance, mask=mask, blockSize=7)
    return np.zeros((0, 2), np.float32) if pts is None else pts.reshape(-1, 2).astype(np.float32)


_LK = dict(winSize=(21, 21), maxLevel=4, criteria=(3, 30, 0.01))  # 3 = COUNT|EPS


def _lk_step(prev: np.ndarray, cur: np.ndarray, pts: np.ndarray, p: TrackParams) -> tuple[np.ndarray, np.ndarray]:
    """Track pts prev→cur with a forward-backward check. Returns (new_pts, ok_mask)."""
    import cv2

    if len(pts) == 0:
        return pts, np.zeros(0, bool)
    p0 = pts.reshape(-1, 1, 2)
    p1, st1, _ = cv2.calcOpticalFlowPyrLK(prev, cur, p0, None, **_LK)
    p0r, st2, _ = cv2.calcOpticalFlowPyrLK(cur, prev, p1, None, **_LK)
    fb = np.linalg.norm((p0 - p0r).reshape(-1, 2), axis=1)
    ok = (st1.ravel() == 1) & (st2.ravel() == 1) & (fb < p.fb_max_err)
    return p1.reshape(-1, 2), ok


def _inside(pts: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    return (pts[:, 0] >= 0) & (pts[:, 0] < w - 1) & (pts[:, 1] >= 0) & (pts[:, 1] < h - 1)


def _free_at(pts: np.ndarray, free: np.ndarray) -> np.ndarray:
    xi = np.clip(np.round(pts[:, 0]).astype(int), 0, free.shape[1] - 1)
    yi = np.clip(np.round(pts[:, 1]).astype(int), 0, free.shape[0] - 1)
    return free[yi, xi] > 0


def _pass(frames: Callable[[int], np.ndarray], subject: Callable[[int], np.ndarray | None], key: int,
          order: Sequence[int], quad_px: np.ndarray, p: TrackParams) -> dict[int, tuple[np.ndarray, float]]:
    """Track in one direction. Each live feature remembers its key-frame position, so every frame's
    homography is estimated key→current directly (no chained-homography drift)."""
    import cv2

    out: dict[int, tuple[np.ndarray, float]] = {}
    prev = frames(key)
    shape = prev.shape
    region = cv2.bitwise_and(_quad_mask(shape, quad_px, p.expand), _subject_free(shape, subject(key), p))
    cur_pts = _detect(prev, region, p)
    key_pts = cur_pts.copy()
    key_img = prev
    H_prev = np.eye(3)
    for f in order:
        cur = frames(f)
        if len(cur_pts) < p.min_inliers:
            break
        nxt, ok = _lk_step(prev, cur, cur_pts, p)
        free = _subject_free(shape, subject(f), p)
        ok &= _inside(nxt, shape) & _free_at(nxt, free)
        nxt, kp, pp = nxt[ok], key_pts[ok], cur_pts[ok]
        if len(nxt) < p.min_inliers:
            break
        H, inl = cv2.findHomography(kp, nxt, cv2.RANSAC, p.ransac_px, maxIters=2000, confidence=0.995)
        if H is None:
            break
        inl = inl.ravel().astype(bool)
        n_in = int(inl.sum())
        conf = float(inl.mean()) * min(1.0, n_in / 40.0)
        if n_in < p.min_inliers:
            break
        refined = False
        vis = _visible_fraction(region, H, shape, free)
        if vis < p.weak_visible and f != key and len(out):
            # Mostly occluded or off screen: a full homography from a small patch of points extrapolates wildly.
            A, a_inl = cv2.estimateAffinePartial2D(pp[inl], nxt[inl], method=cv2.RANSAC, ransacReprojThreshold=p.ransac_px)
            if A is not None:
                H = np.vstack([A, [0, 0, 1]]) @ H_prev
                conf *= max(0.5, vis / p.weak_visible)
        elif p.refine:
            H_ecc, rho = _ecc_refine(key_img, region, cur, free, H, p)
            if H_ecc is not None and rho >= p.ecc_min_rho:
                c_ecc = cv2.perspectiveTransform(quad_px.reshape(-1, 1, 2).astype(np.float64), H_ecc).reshape(4, 2)
                if _sane_quad(c_ecc, quad_px):
                    H, refined = H_ecc, True
                    conf = 0.5 * conf + 0.5 * rho
        corners = cv2.perspectiveTransform(quad_px.reshape(-1, 1, 2).astype(np.float64), H).reshape(4, 2)
        # Reject degenerate/flipped poses (a planar quad stays convex with the same winding).
        if not _sane_quad(corners, quad_px):
            conf = 0.0
        out[f] = (corners, conf)
        cur_pts, key_pts = nxt[inl], kp[inl]
        if refined:
            # Re-anchor the features on the refined plane pose so LK slippage (e.g. along repetitive
            # slats) never accumulates.
            cur_pts = cv2.perspectiveTransform(key_pts.reshape(-1, 1, 2).astype(np.float64), H).reshape(-1, 2).astype(np.float32)
        H_prev = H
        if len(cur_pts) < p.replenish_below:
            reg = cv2.bitwise_and(_quad_mask(shape, corners, p.expand), free)
            fresh = _detect(cur, reg, p, n=p.max_corners)
            if len(fresh):
                if len(cur_pts):
                    d = np.linalg.norm(fresh[:, None, :] - cur_pts[None, :, :], axis=2).min(axis=1)
                    fresh = fresh[d > p.min_distance]
                if len(fresh):
                    back = cv2.perspectiveTransform(fresh.reshape(-1, 1, 2).astype(np.float64), np.linalg.inv(H_prev))
                    cur_pts = np.vstack([cur_pts, fresh]).astype(np.float32)
                    key_pts = np.vstack([key_pts, back.reshape(-1, 2)]).astype(np.float32)
        prev = cur
    return out


def _visible_fraction(key_mask: np.ndarray, H: np.ndarray, shape, free: np.ndarray) -> float:
    import cv2

    ys, xs = np.nonzero(key_mask[::8, ::8])
    if len(xs) == 0:
        return 0.0
    pts = cv2.perspectiveTransform(np.stack([xs * 8, ys * 8], -1).reshape(-1, 1, 2).astype(np.float64), H).reshape(-1, 2)
    return float((_inside(pts, shape) & _free_at(pts, free)).mean())


def _ecc_refine(key_img: np.ndarray, key_mask: np.ndarray, cur: np.ndarray, cur_free: np.ndarray,
                H: np.ndarray, p: TrackParams) -> tuple[np.ndarray | None, float]:
    """Refine a key→current homography by maximizing the enhanced correlation coefficient between the
    key-frame region (template) and the current frame, ignoring the subject in both. Returns (H, rho)."""
    import cv2

    if _visible_fraction(key_mask, H, cur.shape, cur_free) < p.ecc_min_visible:
        return None, 0.0
    s = p.ecc_scale
    S = np.diag([s, s, 1.0])
    small = lambda im, interp: cv2.resize(im, None, fx=s, fy=s, interpolation=interp)
    T = small(key_img, cv2.INTER_AREA).astype(np.float32)
    I = small(cur, cv2.INTER_AREA).astype(np.float32)
    tm = small(key_mask, cv2.INTER_NEAREST)
    im = small(cur_free, cv2.INTER_NEAREST)
    warp = (S @ H @ np.linalg.inv(S)).astype(np.float32)
    try:
        rho, warp = cv2.findTransformECCWithMask(T, I, tm, im, warp, cv2.MOTION_HOMOGRAPHY,
                                                 (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 60, 1e-5), 5)
    except cv2.error:
        return None, 0.0
    return np.linalg.inv(S) @ warp.astype(np.float64) @ S, float(rho)


def _sane_quad(q: np.ndarray, ref: np.ndarray) -> bool:
    def cross_signs(pts):
        s = []
        for i in range(4):
            a, b, c = pts[i], pts[(i + 1) % 4], pts[(i + 2) % 4]
            s.append(np.sign((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])))
        return s
    s, r = cross_signs(q), cross_signs(ref)
    if len(set(s)) != 1 or s[0] != r[0]:
        return False
    area = lambda pts: 0.5 * abs(sum(pts[i][0] * pts[(i + 1) % 4][1] - pts[(i + 1) % 4][0] * pts[i][1] for i in range(4)))
    ratio = area(q) / max(area(ref), 1e-6)
    return 0.1 < ratio < 10


def smooth_corners(track: dict[int, tuple[np.ndarray, float]], radius: int) -> dict[int, tuple[np.ndarray, float]]:
    """Triangular smoothing over ± radius frames, only across contiguous runs (never bridges a gap)."""
    if radius <= 0 or not track:
        return track
    out = {}
    for f, (c, conf) in track.items():
        acc, wsum = np.asarray(c, np.float64) * (radius + 1), float(radius + 1)
        for sign in (-1, 1):
            for d in range(1, radius + 1):
                g = track.get(f + sign * d)
                if g is None:
                    break
                acc = acc + (radius + 1 - d) * np.asarray(g[0], np.float64)
                wsum += radius + 1 - d
        out[f] = (acc / wsum, conf)
    return out


def track_plane(frames: Callable[[int], np.ndarray], n_frames: int, key: int, corners_px: np.ndarray,
                subject: Callable[[int], np.ndarray | None] | None = None,
                params: TrackParams | None = None, progress: Callable[[float], None] | None = None,
                ) -> dict[int, tuple[np.ndarray, float]]:
    """Track a planar quad through a clip. frames(i) → grayscale uint8; subject(i) → alpha uint8 or None.
    Returns {frame: (4×2 corners in px, confidence)} with low-confidence frames dropped."""
    p = params or TrackParams()
    subject = subject or (lambda i: None)
    quad = np.asarray(corners_px, np.float64).reshape(4, 2)
    track: dict[int, tuple[np.ndarray, float]] = {key: (quad.copy(), 1.0)}
    fwd = _pass(frames, subject, key, range(key + 1, n_frames), quad, p)
    if progress:
        progress(0.5)
    bwd = _pass(frames, subject, key, range(key - 1, -1, -1), quad, p)
    track.update(fwd)
    track.update(bwd)
    kept = {f: v for f, v in sorted(track.items()) if v[1] >= p.min_conf}
    return smooth_corners(kept, p.smooth)


# ---- C. reframe virtual camera ---------------------------------------------------------

ASPECTS = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:5": 4 / 5}


def crop_size(src_w: int, src_h: int, aspect: str) -> tuple[float, float]:
    """Largest crop of the given aspect inside the source, in source-normalized (w, h)."""
    a = ASPECTS[aspect]
    src_a = src_w / src_h
    if a <= src_a:
        return a / src_a, 1.0
    return 1.0, src_a / a


def output_size(src_w: int, src_h: int, aspect: str, min_long: int = 1280, max_long: int = 1920) -> tuple[int, int]:
    cw, ch = crop_size(src_w, src_h, aspect)
    pw, ph = cw * src_w, ch * src_h
    long_px = min(max_long, max(min_long, max(pw, ph)))
    s = long_px / max(pw, ph)
    ev = lambda v: max(2, int(round(v * s / 2)) * 2)
    return ev(pw), ev(ph)


def follow_axis(target: Sequence[float | None], size: float, *, fps: float = 24, dead_zone: float = 0.06,
                omega: float = 3.0, lookahead: float = 0.35) -> list[float]:
    """1-D virtual camera for the crop *center* (normalized). Holds missing targets, applies a
    dead-zone around the current center, then a critically damped spring. Offline, so the target
    is shifted ahead by `lookahead` seconds and pre-smoothed, which hides the spring's lag.
    The result is clamped so the crop window stays inside [0, 1]."""
    lo, hi = size / 2, 1 - size / 2
    if hi <= lo:
        return [0.5] * len(target)
    vals: list[float] = []
    last = next((t for t in target if t is not None), 0.5)
    for t in target:
        if t is not None:
            last = t
        vals.append(min(hi, max(lo, last)))
    n = len(vals)
    if n == 0:
        return []
    ahead = int(round(lookahead * fps))
    arr = np.array(vals, float)
    shifted = np.concatenate([arr[ahead:], np.repeat(arr[-1:], min(ahead, n))])[:n] if ahead else arr
    k = max(1, int(round(fps * 0.5)))
    kernel = np.ones(2 * k + 1) / (2 * k + 1)
    padded = np.concatenate([np.repeat(shifted[:1], k), shifted, np.repeat(shifted[-1:], k)])
    goal = np.convolve(padded, kernel, mode="valid")
    dt = 1.0 / fps
    x, v = float(goal[0]), 0.0
    held, following = x, False
    out = []
    for g in goal:
        # Dead zone with hysteresis: stay put while the subject wobbles inside the zone; once it
        # leaves, follow the goal itself until the camera has caught up, then hold again.
        if abs(g - held) > dead_zone:
            following = True
        if following:
            held = g
            if abs(g - x) < dead_zone * 0.25 and abs(v) < 0.02:
                following = False
        a = omega * omega * (held - x) - 2 * omega * v
        v += a * dt
        x += v * dt
        if not lo <= x <= hi:
            x, v = min(hi, max(lo, x)), 0.0
        out.append(x)
    return out


def surface_bias(person_lr: tuple[float, float] | None, surface_lr: tuple[float, float] | None,
                 size: float) -> float | None:
    """Crop-center target that keeps both the person span and an on-screen surface span in view
    when they fit together; otherwise the person wins."""
    if person_lr is None:
        return None if surface_lr is None else (surface_lr[0] + surface_lr[1]) / 2
    pc = (person_lr[0] + person_lr[1]) / 2
    if surface_lr is None:
        return pc
    lo, hi = min(person_lr[0], surface_lr[0]), max(person_lr[1], surface_lr[1])
    if hi - lo <= size * 0.92:
        return (lo + hi) / 2
    return pc


# ---- JSON documents (docs/SCHEMA.md v2) --------------------------------------------------

def surface_track_doc(track: dict[int, tuple[np.ndarray, float]], width: int, height: int, fps: float) -> dict:
    return {"fps": fps, "frames": [
        {"f": int(f), "corners": [[round(float(x) / width, 5), round(float(y) / height, 5)] for x, y in c],
         "conf": round(float(conf), 3)} for f, (c, conf) in sorted(track.items())]}


def occupancy_doc(alphas, width: int, height: int, fps: float, long_cells: int = OCC_LONG) -> dict:
    """alphas: iterable of HxW uint8 alpha frames."""
    cols, rows = occupancy_dims(width, height, long_cells)
    return {"fps": fps, "cols": cols, "rows": rows, "step": 1,
            "frames": [encode_occupancy(occupancy_cells(a, cols, rows)) for a in alphas]}


def _surface_span(surf_by_f: list[dict[int, list]], f: int, axis: int) -> tuple[float, float] | None:
    spans = []
    for s in surf_by_f:
        c = s.get(f)
        if c:
            v = [pt[axis] for pt in c]
            lo, hi = max(0., min(v)), min(1., max(v))
            if hi > lo:
                spans.append((lo, hi))
    if not spans:
        return None
    return min(s[0] for s in spans), max(s[1] for s in spans)


FOCUS_MARGIN = 0.02  # source-normalized padding around a focus box


def resolve_focus(focus, fps: float, n: int) -> list[dict]:
    """Normalize focus regions ({start, end} seconds or {f0, f1} frames, box [x0, y0, x1, y1] normalized,
    optional label, mode "auto" | "pan", margin) into frame ranges [f0, f1) clipped to [0, n)."""
    out = []
    if isinstance(focus, dict):
        focus = focus.get("focus", [focus])
    for r in focus or []:
        box = [float(v) for v in r["box"]]
        if len(box) != 4 or box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError(f"focus box must be [x0, y0, x1, y1] with x1 > x0, y1 > y0: {box}")
        box = [min(1., max(0., v)) for v in box]
        f0 = int(r["f0"]) if "f0" in r else int(round(float(r["start"]) * fps))
        f1 = int(r["f1"]) if "f1" in r else int(round(float(r["end"]) * fps))
        f0, f1 = max(0, f0), min(n, f1)
        if f1 <= f0:
            continue
        mode = r.get("mode") or "auto"
        if mode not in ("auto", "pan"):
            raise ValueError(f"focus mode must be 'auto' or 'pan', not {mode!r}")
        out.append({"f0": f0, "f1": f1, "box": box, "mode": mode,
                    "margin": float(r.get("margin", FOCUS_MARGIN)), "label": r.get("label")})
    out.sort(key=lambda r: r["f0"])
    return out


def _segments(n: int, focus: list[dict]) -> list[tuple[int, int]]:
    cuts = sorted({0, n, *(r["f0"] for r in focus), *(r["f1"] for r in focus)})
    return [(a, b) for a, b in zip(cuts, cuts[1:]) if b > a]


def _clamp_into(c: float, size: float, lo: float, hi: float) -> float:
    """Crop center so that [lo, hi] is inside [c - size/2, c + size/2], moved as little as possible, then
    kept inside the frame."""
    c = min(max(c, hi - size / 2), lo + size / 2)
    return min(1 - size / 2, max(size / 2, c))


def compute_crop(width: int, height: int, fps: float, tracks: dict | None, surfaces: dict[str, dict] | list | None,
                 aspect: str, n: int, track_id: str = "person0", focus=None) -> dict:
    """crop.json (SCHEMA v2 §C) following `track_id` (or the first track) of a tracks.json document,
    biased to keep tracked surfaces ({id: surface-track doc} or a list of them) in view.

    `focus` (see resolve_focus): regions the crop must contain during a time range, e.g. a generated
    word. Each range is its own camera segment (treated like a cut). Inside it the person-following
    camera is clamped so the box stays in frame; when the box is wider/taller than the crop, mode
    "auto" zooms out to the smallest window of the same aspect that holds it (letterboxed: x/y may be
    < 0 and w/h > 1), and mode "pan" keeps the full-height crop and scans across the box."""
    cw, ch = crop_size(width, height, aspect)
    person = None
    if tracks:
        person = next((t for t in tracks.get("tracks", []) if t.get("id") == track_id), None) or \
                 next(iter(tracks.get("tracks", [])), None)
    by_f = {fr["f"]: fr for fr in (person or {}).get("frames", [])}
    surf_list = list(surfaces.values()) if isinstance(surfaces, dict) else list(surfaces or [])
    surf_by_f = [{fr["f"]: fr["corners"] for fr in s.get("frames", [])} for s in surf_list]
    regions = resolve_focus(focus, fps, n)
    region_at = {}
    for r in regions:
        for f in range(r["f0"], r["f1"]):
            region_at[f] = r  # later regions win on overlap
    tx, ty = [], []
    for f in range(n):
        fr = by_f.get(f)
        if fr:
            bx, by, bw, bh = fr["bbox"]
            # Horizontal: mostly the head (faces read best), partly the body; vertical: head at the upper third.
            hx = 0.65 * fr.get("cx", bx + bw / 2) + 0.35 * (bx + bw / 2)
            p_lr = (hx - min(bw, cw) / 2, hx + min(bw, cw) / 2)
            hy = fr.get("cy", by + bh * 0.1) + ch / 6
            px_target = surface_bias(p_lr, _surface_span(surf_by_f, f, 0), cw)
            py_target = surface_bias((hy - 0.05, hy + 0.05), _surface_span(surf_by_f, f, 1), ch)
        else:
            px_target = py_target = None
        r = region_at.get(f)
        if r:
            x0, y0, x1, y1 = r["box"]
            m = r["margin"]
            if x1 - x0 + 2 * m <= cw:
                px_target = _clamp_into((x0 + x1) / 2 if px_target is None else px_target, cw, x0 - m, x1 + m)
            if y1 - y0 + 2 * m <= ch:
                py_target = _clamp_into((y0 + y1) / 2 if py_target is None else py_target, ch, y0 - m, y1 + m)
        tx.append(px_target)
        ty.append(py_target)
    xs, ys = [0.0] * n, [0.0] * n
    for a, b in _segments(n, regions):
        xs[a:b] = follow_axis(tx[a:b], cw, fps=fps)
        ys[a:b] = follow_axis(ty[a:b], ch, fps=fps)
    frames = []
    used = {}
    for f in range(n):
        x, y, w, h = xs[f], ys[f], cw, ch
        r = region_at.get(f)
        if r:
            x0, y0, x1, y1 = r["box"]
            m = r["margin"]
            bw, bh = x1 - x0 + 2 * m, y1 - y0 + 2 * m
            fits = bw <= cw and bh <= ch
            if fits:
                x, y, how = _clamp_into(x, cw, x0 - m, x1 + m), _clamp_into(y, ch, y0 - m, y1 + m), "follow"
            elif r["mode"] == "pan":
                t = (f - r["f0"]) / max(1, r["f1"] - r["f0"] - 1)
                t = t * t * (3 - 2 * t)  # smoothstep: ease in and out
                def scan(lo, hi, size, c):
                    if hi - lo <= size:
                        return _clamp_into(c, size, lo, hi)
                    return min(1 - size / 2, max(size / 2, lo + size / 2 + t * (hi - lo - size)))
                x, y, how = scan(x0 - m, x1 + m, cw, x), scan(y0 - m, y1 + m, ch, y), "pan"
            else:
                k = max(bw / cw, bh / ch)
                w, h = cw * k, ch * k
                # Center on the box, then keep inside the frame on any axis where the window fits;
                # an axis that overflows the frame is letterboxed symmetrically.
                x = min(1 - w / 2, max(w / 2, (x0 + x1) / 2)) if w <= 1 else 0.5
                y = min(1 - h / 2, max(h / 2, (y0 + y1) / 2)) if h <= 1 else 0.5
                how = "zoom"
            used[id(r)] = how
        frames.append({"f": f, "x": round(x - w / 2, 5), "y": round(y - h / 2, 5), "w": round(w, 5), "h": round(h, 5)})
    doc = {"fps": fps, "aspect": aspect, "frames": frames}
    if regions:
        doc["focus"] = [{k: v for k, v in {**r, "applied": used.get(id(r), "none")}.items() if v is not None}
                        for r in regions]
    return doc


def render_crop(img: np.ndarray, fr: dict, out_w: int, out_h: int) -> np.ndarray:
    """Cut one crop.json frame out of an HxWx3 uint8 image at out_w x out_h; areas of a letterboxed
    window (x/y < 0, w/h > 1) outside the source are black."""
    import cv2
    H, W = img.shape[:2]
    sx, sy = out_w / (fr["w"] * W), out_h / (fr["h"] * H)
    M = np.float32([[sx, 0, -fr["x"] * W * sx], [0, sy, -fr["y"] * H * sy]])
    return cv2.warpAffine(img, M, (out_w, out_h), flags=cv2.INTER_AREA if sx < 1 else cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def alignment_score(key_img: np.ndarray, key_mask: np.ndarray, cur: np.ndarray, H: np.ndarray, scale: float = 0.5) -> float:
    """Quality metric for a pose: correlation between the key-frame region and the current frame warped
    back into the key frame with H (1 = perfect). Only key-region pixels that land inside the frame count."""
    import cv2

    h, w = key_img.shape
    back = cv2.warpPerspective(cur, H, (w, h), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)
    valid = cv2.warpPerspective(np.full_like(cur, 255), H, (w, h), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_NEAREST)
    m = cv2.bitwise_and(key_mask, valid)
    sm = lambda im: cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    a, b, mm = sm(key_img).astype(np.float32), sm(back).astype(np.float32), sm(m) > 0
    if mm.sum() < 50:
        return 0.0
    a, b = a[mm] - a[mm].mean(), b[mm] - b[mm].mean()
    return float((a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
