"""Colour/luma key matte for the TD stars (white fill, pink outline on pastel blue) -> project analysis/matte/.

  ~/ComfyUI/.venv/bin/python scripts/content/ffm_key.py <video> <out_dir> [--probe]

Per frame: pink outline (HSV magenta) -> close -> fill holes = silhouette. Where the outline has gaps (fill collapses),
fall back to white pixels inside the dilated previous silhouette + the outline. Soft 2px edge. Writes fg_%05d.png (RGBA
cutout, 1-based) + mask_%05d.png; the server-format fg.webm is encoded separately (see NOTES.md).
"""
import sys, cv2, numpy as np
from pathlib import Path
src, out = sys.argv[1], Path(sys.argv[2]); probe = "--probe" in sys.argv; out.mkdir(parents=True, exist_ok=True)
K = lambda r: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r, r))
def fill(m):
    ff = m.copy(); h, w = ff.shape; msk = np.zeros((h + 2, w + 2), np.uint8); cv2.floodFill(ff, msk, (0, 0), 255); return m | cv2.bitwise_not(ff)
def biggest(m, min_area):
    n, lab, st, _ = cv2.connectedComponentsWithStats(m); keep = np.zeros_like(m)
    for i in range(1, n):
        if st[i, 4] > min_area: keep[lab == i] = 255
    return keep
cap = cv2.VideoCapture(src); ref = None; ref_area = 0; f = 0; areas = []; good = []
while True:
    ok, im = cap.read()
    if not ok: break
    f += 1
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV); h, s, v = [hsv[..., i].astype(int) for i in range(3)]
    pink = ((h >= 135) & (h <= 172) & (s > 40) & (v > 150)).astype(np.uint8) * 255
    mode = "outline"
    for r in (15, 25, 41):   # outline gaps: try larger closings before falling back
        sil = biggest(fill(cv2.morphologyEx(pink, cv2.MORPH_CLOSE, K(r))), 15000); a = int(sil.sum() / 255)
        T = np.median(good[-90:]) if good else None   # running median of accepted outline areas (the stars keep their size)
        if T is None or .85 * T <= a <= 1.18 * T: break
    else:
        # Still broken: white pixels near the last good silhouette (anchored, so bloom cannot grow it) + the outline.
        white = ((s < 45) & (v > 205)).astype(np.uint8) * 255
        cand = (white & cv2.dilate(ref, K(9))) | cv2.dilate(pink, K(5)) | (sil if a <= 1.12 * ref_area else 0)
        sil = cv2.morphologyEx(biggest(fill(cv2.morphologyEx(cand, cv2.MORPH_CLOSE, K(11))), 15000), cv2.MORPH_OPEN, K(7))
        sil &= cv2.dilate(ref, K(25))   # stay near the stars: piano-roll labels / bloom elsewhere never join
        a = int(sil.sum() / 255); mode = "white"
        if a < .85 * ref_area: sil, a, mode = ref.copy(), ref_area, "hold"
    areas.append((f, a, mode))
    if mode == "outline": ref, ref_area = sil, a; good.append(a)
    if probe: continue
    alpha = cv2.GaussianBlur(cv2.erode(sil, K(3)), (5, 5), 0)
    cv2.imwrite(str(out / f"mask_{f:05d}.png"), alpha)
    rgba = np.dstack([im, alpha]); cv2.imwrite(str(out / f"fg_{f:05d}.png"), rgba)
from collections import Counter
print("frames", f, Counter(m for *_, m in areas), "area min/med/max", min(a for _, a, _ in areas), int(np.median([a for _, a, _ in areas])), max(a for _, a, _ in areas))
import json; json.dump(areas, open(str(out / "areas.json"), "w"))
for x in areas[::60]: print(x)
