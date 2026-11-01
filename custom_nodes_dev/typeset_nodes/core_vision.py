"""Typeset core vision — pure numpy/OpenCV/Pillow logic shared by the ComfyUI nodes in this pack
and by the Typeset server's in-process fallback (server/app/vision.py loads this file; there is one copy).

  occupancy_*      MASK → coarse grid of "how much subject is in each cell" (where text stays readable)
  track_plane      planar homography tracker for a 4-corner quad on a wall/sign, subject masked out
  compute_crop     smoothed virtual camera (dead zone + critically damped follow) for reframing
  flow_*           dense optical flow (DIS) → coarse per-frame motion field that pushes and smears the type

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
    # Model selection (robust pass): every frame gets translation, similarity and homography candidates (direct
    # masked ECC on high-passed images, plus the feature homography); a richer model must beat a simpler one by
    # a margin of alignment score. Blank / low-texture walls let a homography fit noise and skew; this stops it.
    robust: bool = True
    select_scale: float = 0.5     # alignment work scale
    hp_sigma: float = 6.0         # high-pass (at select_scale) so light falloff doesn't drive the fit
    margin_sim: float = 0.01      # similarity must beat translation by this NCC
    margin_h: float = 0.02        # homography must beat the best low-DOF model by this NCC...
    margin_h_low_texture: float = 0.06  # ...or by this much when the key region has little trackable texture
    low_texture_features: int = 150     # fewer good features than this in the key region = low texture
    ncc_good: float = 0.45        # alignment NCC that maps to confidence 1
    ncc_lost: float = 0.1         # below this the surface is lost (cut, fully occluded); 3 in a row ends the pass
    max_area_drift: float = 6.0   # sanity vs key frame: area ratio outside [1/x, x] = rejected
    max_aspect_drift: float = 3.5 # side-length ratio change vs key frame
    max_skew_deg: float = 50.0    # corner angle change vs key frame
    soft_drift: tuple = (2.5, 2.0, 30.0)  # beyond these (area, aspect, skew) a homography needs a stronger score
    max_step: float = 0.12        # corner jump per frame (fraction of the quad diagonal) = suspicious
    max_gap: int = 3              # lost frames tolerated inside a track before it ends
    robust_expand: float = 1.0    # margin for direct alignment; lower it when the margin reaches other planes (sky,
                                  # buildings above a wall) that move differently and make the text slide
    occ_visible: float = 0.35     # less of the template visible than this (subject in front) = occluded frame
    model_window: float = 8.0     # frames (gaussian sigma) over which a richer model must keep beating a simpler one
    occ_trust: float = 0.18       # subject covering more of the quad than this: frame is interpolated, not trusted
    cut_ncc: float = 0.5          # consecutive-frame thumbnail correlation below this = shot cut: the pass ends


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


def _shape_stats(q: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """(area, side lengths ×4, corner angles in degrees ×4) of a quad."""
    q = np.asarray(q, np.float64)
    area = 0.5 * abs(sum(q[i][0] * q[(i + 1) % 4][1] - q[(i + 1) % 4][0] * q[i][1] for i in range(4)))
    sides = np.array([np.linalg.norm(q[(i + 1) % 4] - q[i]) for i in range(4)])
    ang = []
    for i in range(4):
        a, b = q[i - 1] - q[i], q[(i + 1) % 4] - q[i]
        ang.append(math.degrees(math.acos(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9), -1, 1))))
    return area, sides, np.array(ang)


def quad_drift(q: np.ndarray, ref: np.ndarray) -> dict[str, float]:
    """Shape change of q vs ref: area ratio, worst side-ratio change (aspect), worst corner-angle change (skew)."""
    a0, s0, g0 = _shape_stats(ref)
    a1, s1, g1 = _shape_stats(q)
    r = (s1 / np.maximum(s0, 1e-6))
    return {"area": a1 / max(a0, 1e-6), "aspect": float(r.max() / max(r.min(), 1e-6)), "skew": float(np.abs(g1 - g0).max())}


def _quad_ok(q: np.ndarray, ref: np.ndarray, p: TrackParams) -> bool:
    if not _sane_quad(q, ref):
        return False
    d = quad_drift(q, ref)
    return (1 / p.max_area_drift < d["area"] < p.max_area_drift and d["aspect"] < p.max_aspect_drift
            and d["skew"] < p.max_skew_deg)


class _Aligner:
    """Masked high-pass images at a reduced scale; scores and refines key→frame poses (3×3, full-res px)."""

    def __init__(self, key_img: np.ndarray, key_region: np.ndarray, p: TrackParams):
        self.p, self.s = p, p.select_scale
        self.S = np.diag([self.s, self.s, 1.0])
        self.Si = np.linalg.inv(self.S)
        self.tm = self.small(key_region, nearest=True)
        self.T = self.hp(key_img, self.tm)

    def small(self, im, nearest=False):
        import cv2
        return cv2.resize(im, None, fx=self.s, fy=self.s, interpolation=cv2.INTER_NEAREST if nearest else cv2.INTER_AREA)

    def hp(self, img, free_s=None):
        """High-pass at the work scale. Masked-out pixels (subject) are first filled from the surrounding wall
        (normalized convolution) so the subject's silhouette leaves no edge halo for the alignment to lock onto."""
        import cv2
        s = self.small(img).astype(np.float32)
        if free_s is not None:
            m = (free_s > 0).astype(np.float32)
            if m.min() < 1:
                sig = 3 * self.p.hp_sigma
                num, den = cv2.GaussianBlur(s * m, (0, 0), sig), cv2.GaussianBlur(m, (0, 0), sig)
                fill = np.where(den > 1e-3, num / np.maximum(den, 1e-3), float(s[m > 0].mean()) if m.any() else 0.0)
                s = s * m + fill * (1 - m)
        return s - cv2.GaussianBlur(s, (0, 0), self.p.hp_sigma)

    def score(self, cur_hp, cur_free_s, H) -> float:
        """NCC between the key region and the current frame warped back with H (subject masked in both)."""
        import cv2
        if H is None:
            return -1.0
        Hs = self.S @ H @ self.Si
        h, w = self.T.shape
        try:
            back = cv2.warpPerspective(cur_hp, Hs, (w, h), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)
            valid = cv2.warpPerspective(cur_free_s, Hs, (w, h), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_NEAREST)
        except cv2.error:
            return -1.0
        m = (self.tm > 0) & (valid > 0)
        if m.sum() < 200:
            return -1.0
        a, b = self.T[m], back[m]
        a, b = a - a.mean(), b - b.mean()
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    def search_t(self, cur_hp, H0, radius: int) -> np.ndarray | None:
        """Coarse translation by masked template matching at half the work scale (the low-texture / large-motion
        fallback where ECC has no basin): key region vs a window around where H0 puts it. Returns a translation pose."""
        import cv2
        ys, xs = np.nonzero(self.tm)
        if len(xs) < 50:
            return None
        h, w = self.T.shape
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        c = np.array([[(x0 + x1) / 2, (y0 + y1) / 2]], np.float64) / self.s
        dc = (cv2.perspectiveTransform(c.reshape(-1, 1, 2), H0).reshape(2) - c.reshape(2)) * self.s
        tx, ty = int(round(dc[0])), int(round(dc[1]))
        sx0, sy0 = max(0, x0 + tx - radius), max(0, y0 + ty - radius)
        sx1, sy1 = min(w, x1 + tx + radius), min(h, y1 + ty + radius)
        # crop the template to the part that can still be inside the search window
        cx0, cy0 = max(x0, sx0 - tx - radius), max(y0, sy0 - ty - radius)
        cx1, cy1 = min(x1, sx1 - tx + radius), min(y1, sy1 - ty + radius)
        cx0, cy0 = max(cx0, x0), max(cy0, y0)
        if cx1 - cx0 < 16 or cy1 - cy0 < 16 or sx1 - sx0 < cx1 - cx0 or sy1 - sy0 < cy1 - cy0:
            return None
        down = lambda im: cv2.resize(im, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA)
        tpl, msk = down(self.T[cy0:cy1, cx0:cx1]), down((self.tm[cy0:cy1, cx0:cx1] > 0).astype(np.float32))
        win = down(cur_hp[sy0:sy1, sx0:sx1])
        if msk.sum() < 30 or win.shape[0] < tpl.shape[0] or win.shape[1] < tpl.shape[1]:
            return None
        try:
            res = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED, mask=msk)
        except cv2.error:
            return None
        res = np.nan_to_num(res, nan=-1, posinf=-1, neginf=-1)
        _, _, _, loc = cv2.minMaxLoc(res)
        dx = (sx0 + 2 * loc[0] - cx0) / self.s
        dy = (sy0 + 2 * loc[1] - cy0) / self.s
        return np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]], np.float64)

    def ecc(self, cur_hp, cur_free_s, H0, motion) -> np.ndarray | None:
        import cv2
        W0 = (self.S @ H0 @ self.Si).astype(np.float32)
        if motion != cv2.MOTION_HOMOGRAPHY:
            W0 = W0[:2] / W0[2, 2]
            if motion == cv2.MOTION_TRANSLATION:
                W0 = np.float32([[1, 0, W0[0, 2]], [0, 1, W0[1, 2]]])
        try:
            _, Wr = cv2.findTransformECCWithMask(self.T, cur_hp, self.tm, cur_free_s, W0, motion,
                                                 (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 50, 1e-5), 5)
        except cv2.error:
            return None
        Wr = Wr.astype(np.float64)
        if Wr.shape[0] == 2:
            Wr = np.vstack([Wr, [0, 0, 1]])
        return self.Si @ Wr @ self.S


def _content_mask(img: np.ndarray, margin: int) -> np.ndarray:
    """255 except letterbox / pillarbox padding (flat near-black rows and columns) and a margin around it: the
    padding edge is a strong, motion-invariant line that would otherwise anchor the alignment."""
    m = np.full(img.shape, 255, np.uint8)
    flat = lambda a, ax: (a.mean(axis=ax) < 10) & (a.std(axis=ax) < 4)
    rows, cols = flat(img, 1), flat(img, 0)
    h, w = img.shape
    top = int(np.argmin(rows)) if rows.any() and not rows.all() else 0
    bot = h - int(np.argmin(rows[::-1])) if rows.any() and not rows.all() else h
    left = int(np.argmin(cols)) if cols.any() and not cols.all() else 0
    right = w - int(np.argmin(cols[::-1])) if cols.any() and not cols.all() else w
    if top > 0: m[:min(h, top + margin)] = 0
    if bot < h: m[max(0, bot - margin):] = 0
    if left > 0: m[:, :min(w, left + margin)] = 0
    if right < w: m[:, max(0, right - margin):] = 0
    return m


def _similarity_from(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Closest similarity (rotation, uniform scale, translation) to H over pts (least squares, Umeyama)."""
    import cv2
    src = np.asarray(pts, np.float64)
    dst = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H).reshape(-1, 2)
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    U, D, Vt = np.linalg.svd(b.T @ a)
    R = U @ np.diag([1, np.sign(np.linalg.det(U @ Vt))]) @ Vt
    sc = D.sum() / max((a ** 2).sum(), 1e-9) if np.linalg.det(U @ Vt) > 0 else (D[0] - D[1]) / max((a ** 2).sum(), 1e-9)
    t = md - sc * R @ ms
    return np.vstack([np.hstack([sc * R, t[:, None]]), [0, 0, 1]])


def _robust_pass(frames, subject, key: int, order: Sequence[int], quad: np.ndarray, p: TrackParams,
                 feat: dict[int, tuple[np.ndarray, float]], low_texture: bool) -> dict[int, tuple[np.ndarray, float, str]]:
    """Key-referenced direct alignment with model selection. Each frame: translation and similarity (ECC from the
    previous pose), homography (ECC + the feature tracker's pose); keep the simplest model whose alignment score
    the richer ones don't beat by a margin, and only well-conditioned homographies (sane shape vs the key frame)."""
    import cv2

    key_img = frames(key)
    shape = key_img.shape
    region = cv2.bitwise_and(_quad_mask(shape, quad, min(p.expand, p.robust_expand)), _subject_free(shape, subject(key), p))
    region = cv2.bitwise_and(region, _content_mask(key_img, int(3 * p.hp_sigma / p.select_scale)))
    al = _Aligner(key_img, region, p)
    q32 = quad.reshape(-1, 1, 2)
    out: dict[int, tuple[np.ndarray, float, str]] = {}
    prev, prev_low, prev_model, lost = np.eye(3), np.eye(3), "T", 0
    hist = [quad.copy()]
    last_c = quad.copy()
    diag = float(np.linalg.norm(quad[2] - quad[0]))
    margin_h = p.margin_h_low_texture if low_texture else p.margin_h
    thumb = lambda im: cv2.resize(im, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
    prev_thumb = thumb(key_img)
    for f in order:
        cur = frames(f)
        t = thumb(cur)
        a, b = t - t.mean(), prev_thumb - prev_thumb.mean()
        if float(a.ravel() @ b.ravel() / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)) < p.cut_ncc:
            break  # shot cut: the plane is gone
        prev_thumb = t
        free = _subject_free(shape, subject(f), p)
        cfree = al.small(free, nearest=True)
        chp = al.hp(cur, cfree)
        jump_ok = lambda Hx: np.abs(cv2.perspectiveTransform(q32, Hx).reshape(4, 2) - last_c).max() <= p.max_step * diag
        cands: dict[str, tuple[np.ndarray, float]] = {}
        # constant-velocity prediction from the last few accepted frames (corner space)
        vel = np.mean(np.diff(np.array(hist[-6:]), axis=0), axis=0) if len(hist) >= 2 else np.zeros((4, 2))
        pred_c = last_c + vel
        pred = cv2.getPerspectiveTransform(np.float32(quad), np.float32(pred_c)).astype(np.float64)

        def offer(name, Hx):
            if Hx is None or not np.all(np.isfinite(Hx)) or not jump_ok(Hx):
                return
            sc = al.score(chp, cfree, Hx)
            if name not in cands or sc > cands[name][1]:
                cands[name] = (Hx, sc)
        # translation: ECC from the last pose and from the last low-DOF pose, plus a coarse search (+ ECC)
        for H0 in (pred, prev, prev_low):
            offer("T", al.ecc(chp, cfree, H0, cv2.MOTION_TRANSLATION))
        Hc = al.search_t(chp, prev_low, radius=24)
        if Hc is not None:
            offer("T", Hc)
            offer("T", al.ecc(chp, cfree, Hc, cv2.MOTION_TRANSLATION))
        # similarity: affine ECC from the best translation, projected onto rotation + uniform scale
        Ha = al.ecc(chp, cfree, cands["T"][0] if "T" in cands else prev_low, cv2.MOTION_AFFINE)
        if Ha is not None and np.all(np.isfinite(Ha)):
            offer("S", _similarity_from(Ha, quad))
        # homography: feature tracker's pose and ECC from the best low-DOF pose / last homography, only if well-conditioned
        homs = []
        if f in feat and feat[f][1] > 0:
            homs.append(cv2.getPerspectiveTransform(np.float32(quad), np.float32(feat[f][0])))
        low_best = max((cands[k] for k in ("T", "S") if k in cands), key=lambda v: v[1], default=(prev, 0))[0]
        vis = _visible_fraction(region, low_best, shape, free)
        if vis >= p.ecc_min_visible:
            for H0 in [low_best] + ([prev] if prev_model == "H" else []):
                homs.append(al.ecc(chp, cfree, H0, cv2.MOTION_HOMOGRAPHY))
        h_far = False
        for Hh in homs:
            if Hh is None or not np.all(np.isfinite(Hh)):
                continue
            c = cv2.perspectiveTransform(q32, Hh).reshape(4, 2)
            if not _quad_ok(c, quad, p) or not jump_ok(Hh):
                continue
            sc = al.score(chp, cfree, Hh)
            if "H" not in cands or sc > cands["H"][1]:
                d = quad_drift(c, quad)
                cands["H"] = (Hh, sc)
                h_far = not (1 / p.soft_drift[0] < d["area"] < p.soft_drift[0] and d["aspect"] < p.soft_drift[1]
                             and d["skew"] < p.soft_drift[2])
        # how much of the key-frame template the subject hides right now (off-screen parts don't count)
        cover = _subject_cover(region, pred, shape, free)
        occluded = cover > 1 - p.occ_visible
        if occluded:
            # template mostly hidden: an estimate must be convincing AND agree with the motion so far, else carry the
            # pose forward at constant velocity
            tol = max(3.0, 0.03 * diag)
            cands = {k: v for k, v in cands.items() if v[1] >= 0.6 * p.ncc_good
                     and np.abs(cv2.perspectiveTransform(q32, v[0]).reshape(4, 2) - pred_c).max() <= tol}
        if not cands:
            if occluded:
                pc = cv2.perspectiveTransform(q32, pred).reshape(4, 2)
                out[f] = (pc, 0.0, "P", {"c": {"P": (pc, 0.0)}, "occ": 1.0, "far": False})
                prev, last_c = pred, pc
                hist.append(pc)
                continue
            lost += 1
            if lost >= 3:
                break
            continue
        # simplest model unless a richer one is clearly better (half the margin for the model already in use)
        m = lambda name, base: base * (0.5 if name == prev_model else 1.0)
        best = "T" if "T" in cands else next(iter(cands))
        if "S" in cands and (best == "S" or cands["S"][1] > cands[best][1] + m("S", p.margin_sim)):
            best = "S"
        if "H" in cands and best != "H" and cands["H"][1] > cands[best][1] + m("H", margin_h) + (0.05 if h_far else 0.0):
            best = "H"
        H, sc = cands[best]
        corners = cv2.perspectiveTransform(q32, H).reshape(4, 2)
        conf = float(np.clip(sc / p.ncc_good, 0, 1))
        if not _quad_ok(corners, quad, p):
            conf = 0.0
        elif best == "H" and h_far:
            conf *= 0.8
        if sc < p.ncc_lost and not occluded:
            lost += 1
            if lost >= 3:
                break
        else:
            lost = 0
        # every candidate's corners + score, and how much of the quad the subject covers (for the trajectory stage)
        allc = {k: (cv2.perspectiveTransform(q32, v[0]).reshape(4, 2), v[1]) for k, v in cands.items()}
        occ = max(_occlusion(corners, free), cover)
        out[f] = (corners, conf, best, {"c": allc, "occ": occ, "far": h_far})
        prev, prev_model, last_c = H, best, corners
        hist.append(corners)
        if best in ("T", "S"):
            prev_low = H
        else:
            prev_low = cands.get("S", cands.get("T", (_similarity_from(H, quad), 0)))[0]
    return out


def _subject_cover(key_mask: np.ndarray, H: np.ndarray, shape, free: np.ndarray) -> float:
    """Fraction of the in-frame part of the key-frame template that the subject covers under pose H."""
    import cv2
    ys, xs = np.nonzero(key_mask[::8, ::8])
    if len(xs) == 0:
        return 0.0
    pts = cv2.perspectiveTransform(np.stack([xs * 8, ys * 8], -1).reshape(-1, 1, 2).astype(np.float64), H).reshape(-1, 2)
    ins = _inside(pts, shape)
    if ins.sum() == 0:
        return 0.0
    return float((~_free_at(pts[ins], free)).mean())


def _occlusion(corners: np.ndarray, free: np.ndarray) -> float:
    """Fraction of the in-frame part of the quad covered by the (dilated) subject."""
    import cv2
    h, w = free.shape
    m = np.zeros((h // 4 + 1, w // 4 + 1), np.uint8)
    cv2.fillConvexPoly(m, np.round(np.asarray(corners) / 4).astype(np.int32), 1)
    m = m[:h // 4, :w // 4] > 0
    if m.sum() < 4:
        return 0.0
    sub = free[::4, ::4][:m.shape[0], :m.shape[1]] == 0
    return float((sub & m).sum() / m.sum())


def _local_linear(fs: np.ndarray, X: np.ndarray, w: np.ndarray, sigma: float) -> np.ndarray:
    """Weighted local-linear (Gaussian kernel) smoothing of trajectories X[n, d] over frames fs: no lag on a pan,
    no edge bias at the ends of a run; low-weight frames (occluded, weak) follow their neighbours."""
    out = np.empty_like(X)
    for i, f in enumerate(fs):
        d = fs - f
        k = np.exp(-0.5 * (d / sigma) ** 2) * w
        sel = k > 1e-6 * k.max()
        dd, kk, XX = d[sel].astype(np.float64), k[sel], X[sel]
        S0, S1, S2 = kk.sum(), (kk * dd).sum(), (kk * dd * dd).sum()
        den = S0 * S2 - S1 * S1
        if den <= 1e-9 * max(S0 * S2, 1e-12):
            out[i] = (kk[:, None] * XX).sum(0) / S0
            continue
        T0, T1 = (kk[:, None] * XX).sum(0), (kk[:, None] * dd[:, None] * XX).sum(0)
        out[i] = (S2 * T0 - S1 * T1) / den
    return out


def _consolidate(rob: dict, key: int, quad: np.ndarray, p: TrackParams, low: bool, n_frames: int, info: dict | None):
    """Trajectory stage. Richer models are blended in softly: a frame's similarity / homography weight comes from that
    model's score gain over the simpler one *smoothed over a window of frames* (so one lucky frame never switches the
    model), mapped through a margin ramp. Frames where the subject covers the quad or the score is weak are
    down-weighted, then a weighted local-linear low-pass over the corner trajectory."""
    fs_all = sorted(f for f in rob if f != key)
    if not fs_all:
        return {key: (quad.copy(), 1.0)}
    mh = p.margin_h_low_texture if low else p.margin_h
    idx = np.array(fs_all, np.float64)
    occ = np.array([rob[f][3]["occ"] for f in fs_all])
    def score(f, m):
        c = rob[f][3]["c"]
        return c[m][1] if m in c else None
    def gain_track(a, b, margin):
        g, w = [], []
        for f in fs_all:
            sa, sb = score(f, a), score(f, b)
            if sa is None or sb is None:
                g.append(-margin); w.append(0.3)  # richer model missing here: counts against it
            else:
                g.append(sa - sb); w.append(max(0.1, 1 - rob[f][3]["occ"]))
        g, w = np.array(g), np.array(w)
        gs = _local_linear(idx, g[:, None], w, p.model_window)[:, 0] if len(g) > 2 else g
        return np.clip((gs - 0.5 * margin) / margin, 0, 1)
    aS = gain_track("S", "T", p.margin_sim)
    aH = gain_track("H", "T", mh)
    recs = {}
    for i, f in enumerate(fs_all):
        c = rob[f][3]["c"]
        if "P" in c and len(c) == 1:
            recs[f] = [c["P"][0], 0.0, 0.002, 1.0]
            continue
        base = c.get("T", c.get("S", c.get("H")))
        cs = c.get("S", base); ch = c.get("H", None)
        low_c = (1 - aS[i]) * base[0] + aS[i] * cs[0]
        corners = low_c if ch is None else (1 - aH[i]) * low_c + aH[i] * ch[0]
        sc = max(v[1] for k, v in c.items() if k != "P")
        if not _quad_ok(corners, quad, p):
            continue
        conf = float(np.clip(sc / p.ncc_good, 0, 1)) * (0.8 if ch is not None and aH[i] > .5 and rob[f][3]["far"] else 1.0)
        w = max(conf, 0.02)
        o = rob[f][3]["occ"]
        if o > p.occ_trust:
            w *= max(0.05, (1 - o) ** 2)  # subject over the quad: lean on less-occluded neighbours
        recs[f] = [corners, conf, w, o]
    model = "H" if aH.mean() > .5 else "S" if aS.mean() > .5 else "T"
    recs[key] = [quad.copy(), 1.0, 20.0, 0.0]
    # connected run around the key: occluded frames never end a track; weak *unoccluded* frames do
    trusted = lambda f: f in recs and (recs[f][1] >= p.min_conf or recs[f][3] > p.occ_trust)
    run = {key}
    for step in (1, -1):
        f, gap = key + step, 0
        while 0 <= f < n_frames and gap <= p.max_gap:
            if trusted(f):
                run.add(f); gap = 0
            else:
                gap += 1
            f += step
    fs = np.array(sorted(f for f in run if f in recs))
    X = np.stack([recs[f][0].reshape(8) for f in fs])
    W = np.array([recs[f][2] for f in fs])
    C = np.array([recs[f][1] for f in fs])
    sigma = p.smooth * (2.5 if low else 1.5)
    Xs = _local_linear(fs, X, W, sigma) if sigma > 0 and len(fs) > 2 else X
    # confidence of occluded frames comes from their unoccluded neighbours
    occl = np.array([recs[f][3] > p.occ_trust for f in fs])
    if occl.any() and (~occl).any():
        cn = _local_linear(fs, C[:, None], np.where(occl, 1e-3, 1.0), max(sigma, 3.0))[:, 0]
        C = np.where(occl, np.maximum(C, np.clip(cn, 0, 1)), C)
    if info is not None:
        info.update({"model": model, "occluded": int(occl.sum()), "sigma": sigma})
    return {int(f): (Xs[i].reshape(4, 2), float(C[i])) for i, f in enumerate(fs) if C[i] >= p.min_conf or f == key}


def smooth_corners_gauss(track: dict[int, tuple[np.ndarray, float]], sigma: float) -> dict[int, tuple[np.ndarray, float]]:
    """Gaussian smoothing of corners over contiguous runs (edge-normalized; never bridges a gap)."""
    if sigma <= 0 or not track:
        return track
    r = int(math.ceil(2.5 * sigma))
    out = {}
    for f, (c, conf) in track.items():
        acc, wsum = np.zeros((4, 2)), 0.0
        for sign in (-1, 1):
            for d in range(0 if sign < 0 else 1, r + 1):
                g = track.get(f + sign * d)
                if g is None:
                    break
                w = math.exp(-0.5 * (d / sigma) ** 2)
                acc, wsum = acc + w * np.asarray(g[0], np.float64), wsum + w
        out[f] = (acc / wsum, conf)
    return out


def texture_features(img: np.ndarray, quad_px: np.ndarray, subject_alpha: np.ndarray | None, p: TrackParams) -> int:
    """How many good features the (expanded) key-frame quad offers, subject masked out."""
    import cv2
    region = cv2.bitwise_and(_quad_mask(img.shape, np.asarray(quad_px, np.float64), p.expand), _subject_free(img.shape, subject_alpha, p))
    return len(_detect(img, region, p))


def track_plane(frames: Callable[[int], np.ndarray], n_frames: int, key: int, corners_px: np.ndarray,
                subject: Callable[[int], np.ndarray | None] | None = None,
                params: TrackParams | None = None, progress: Callable[[float], None] | None = None,
                info: dict | None = None) -> dict[int, tuple[np.ndarray, float]]:
    """Track a planar quad through a clip. frames(i) → grayscale uint8; subject(i) → alpha uint8 or None.
    Returns {frame: (4×2 corners in px, confidence)} with low-confidence frames dropped.

    Feature pass (LK + RANSAC homography + ECC refine) → robust pass that re-estimates every frame directly against
    the key frame and picks translation / similarity / homography by alignment score (with margins, stricter on
    low-texture walls) → shape sanity vs the key frame → confidence from alignment → temporal smoothing.
    `info` (optional dict) receives {"low_texture", "features", "models": {T,S,H counts}}."""
    p = params or TrackParams()
    subject = subject or (lambda i: None)
    quad = np.asarray(corners_px, np.float64).reshape(4, 2)
    track: dict[int, tuple[np.ndarray, float]] = {key: (quad.copy(), 1.0)}
    fwd = _pass(frames, subject, key, range(key + 1, n_frames), quad, p)
    if progress:
        progress(0.25 if p.robust else 0.5)
    bwd = _pass(frames, subject, key, range(key - 1, -1, -1), quad, p)
    track.update(fwd)
    track.update(bwd)
    if not p.robust:
        kept = {f: v for f, v in sorted(track.items()) if v[1] >= p.min_conf}
        return smooth_corners(kept, p.smooth)
    n_feat = texture_features(frames(key), quad, subject(key), p)
    low = n_feat < p.low_texture_features
    rob = _robust_pass(frames, subject, key, range(key + 1, n_frames), quad, p, track, low)
    if progress:
        progress(0.75)
    rob.update(_robust_pass(frames, subject, key, range(key - 1, -1, -1), quad, p, track, low))
    if info is not None:
        info.update({"low_texture": low, "features": n_feat,
                     "per_frame_best": {m: sum(1 for v in rob.values() if v[2] == m) for m in "TSH"}})
    return _consolidate(rob, key, quad, p, low, n_frames, info)


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


# ---- subject tracks (tracks.json, SCHEMA §2) from mattes processed in chunks -------------------

def _moving_average(values, window):
    if window <= 1 or len(values) < 2:
        return list(values)
    half = window // 2
    out = []
    for i in range(len(values)):
        lo, hi = max(0, i - half), min(len(values), i + half + 1)
        out.append(float(np.mean(values[lo:hi])))
    return out


def smooth_track_frames(frames: list[dict], smooth: int) -> list[dict]:
    """Moving average of cx/cy over runs of consecutive frames (gaps don't bleed), then round to 4 dp.
    `frames` hold raw (unrounded) anchors; bbox is left as is."""
    frames = [dict(fr) for fr in sorted(frames, key=lambda fr: fr["f"])]
    if smooth and smooth > 1 and frames:
        runs, cur = [], [frames[0]]
        for fr in frames[1:]:
            if fr["f"] == cur[-1]["f"] + 1:
                cur.append(fr)
            else:
                runs.append(cur)
                cur = [fr]
        runs.append(cur)
        for run in runs:
            cxs = _moving_average([r["cx"] for r in run], smooth)
            cys = _moving_average([r["cy"] for r in run], smooth)
            for r, cx, cy in zip(run, cxs, cys):
                r["cx"], r["cy"] = cx, cy
    for fr in frames:
        fr["cx"], fr["cy"] = round(fr["cx"], 4), round(fr["cy"], 4)
    return frames


def merge_track_chunks(chunks: list[dict], fps: float, total_frames: int, smooth: int = 3) -> dict:
    """Join raw tracks.json documents of consecutive chunks (MaskToTracks with raw=True and frame_offset)
    into one tracks.json, smoothing across chunk boundaries exactly as a single pass would."""
    first = next((t for c in chunks for t in c.get("tracks", [])), None) or {"id": "person0", "label": "person"}
    frames = [fr for c in chunks for t in c.get("tracks", []) if t.get("id") == first["id"] for fr in t.get("frames", [])]
    return {"fps": float(fps), "frames": int(total_frames),
            "tracks": [{"id": first["id"], "label": first.get("label", "person"),
                        "frames": smooth_track_frames(frames, smooth)}]}


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


# ---- F. motion field -------------------------------------------------------------------
# Per frame f: the motion from f-1 to f, sampled on a coarse grid, in normalized units (fraction of width /
# height per frame). Quantized to int8 against one clip-wide `scale`, base64 per frame (like occupancy).

FLOW_LONG = 64  # grid cells along the long edge
FLOW_WORK = 320  # long edge the flow is computed at (DIS is fast; detail beyond this is noise for type)


def flow_dims(width: int, height: int, long_cells: int = FLOW_LONG) -> tuple[int, int]:
    return occupancy_dims(width, height, long_cells)


def flow_grids(grays: Sequence[np.ndarray], cols: int, rows: int, work_long: int = FLOW_WORK) -> list[np.ndarray]:
    """grays: HxW uint8 frames → rows×cols×2 float32 grids (dx/W, dy/H); frame 0 is zero."""
    import cv2
    if not grays:
        return []
    h, w = grays[0].shape[:2]
    k = work_long / max(w, h)
    size = (max(16, round(w * k)), max(16, round(h * k)))
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    out = [np.zeros((rows, cols, 2), np.float32)]
    prev = cv2.resize(grays[0], size, interpolation=cv2.INTER_AREA)
    for g in grays[1:]:
        cur = cv2.resize(g, size, interpolation=cv2.INTER_AREA)
        flow = dis.calc(prev, cur, None)
        grid = cv2.resize(flow, (cols, rows), interpolation=cv2.INTER_AREA)
        grid[..., 0] /= size[0]
        grid[..., 1] /= size[1]
        out.append(grid.astype(np.float32))
        prev = cur
    return out


def flow_doc(grids: list[np.ndarray], fps: float) -> dict:
    rows, cols = grids[0].shape[:2] if grids else (0, 0)
    mags = np.concatenate([np.abs(g).ravel() for g in grids]) if grids else np.zeros(1)
    scale = float(max(np.percentile(mags, 99.7), 1e-4))
    def enc(g):
        q = np.clip(np.round(g / scale * 127), -127, 127).astype(np.int8)
        return base64.b64encode(q.tobytes()).decode("ascii")
    return {"fps": fps, "cols": int(cols), "rows": int(rows), "scale": round(scale, 6), "frames": [enc(g) for g in grids]}


def decode_flow(data: str, cols: int, rows: int, scale: float) -> np.ndarray:
    return np.frombuffer(base64.b64decode(data), np.int8).reshape(rows, cols, 2).astype(np.float32) * (scale / 127)


def flow_preview(grid: np.ndarray, scale: float, size: tuple[int, int]) -> np.ndarray:
    """HSV flow picture (hue = direction, value = speed) at size (w, h), RGB uint8."""
    import cv2
    ang = (np.degrees(np.arctan2(grid[..., 1], grid[..., 0])) % 360) / 2
    mag = np.clip(np.hypot(grid[..., 0], grid[..., 1]) / max(scale, 1e-6), 0, 1) * 255
    hsv = np.dstack([ang, np.full_like(ang, 200), mag]).astype(np.uint8)
    return cv2.resize(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), size, interpolation=cv2.INTER_NEAREST)
