"""Side-by-side review of an H3 take vs its lip-synced version, plus a frame strip of the mouth region.
usage: lipsync_compare.py <take_dir> <tag> [n_frames]
writes <take_dir>/<tag>/strip.jpg (top row = H3 take, bottom row = lip-synced; mouth crops at evenly spaced frames)
and <take_dir>/<tag>/compare.mp4 (left = H3 take, right = lip-synced, song audio).
"""
import subprocess, sys
from pathlib import Path
import cv2, numpy as np

take = Path(sys.argv[1]); tag = sys.argv[2]; n = int(sys.argv[3]) if len(sys.argv) > 3 else 12
name = take.name
a = take / f"{name}_mux.mp4"; b = take / tag / f"{name}_{tag}_mux.mp4"
out_dir = take / tag


def frames(path):
    cap = cv2.VideoCapture(str(path)); fs = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fs.append(f)
    return fs


# mouth strip: OpenCV's haar cascade finds the face box (good enough for a crop); crop the lower half of the face
cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
fa, fb = frames(a), frames(b)
m = min(len(fa), len(fb)); idx = np.linspace(0, m - 1, n).astype(int)
tiles_a, tiles_b = [], []
box = None
W = 220
for i in idx:
    g = cv2.cvtColor(fa[i], cv2.COLOR_BGR2GRAY)
    det = cas.detectMultiScale(g, 1.1, 5, minSize=(120, 120))
    if len(det):
        x, y, w, h = max(det, key=lambda d: d[2] * d[3]); box = (int(x), int(y), int(w), int(h))
    if box is None:
        continue
    x, y, w, h = box
    y0, y1 = max(0, int(y + h * 0.5)), int(y + h * 1.08); x0, x1 = max(0, int(x + w * 0.1)), int(x + w * 0.9)
    for src, tiles in ((fa, tiles_a), (fb, tiles_b)):
        crop = src[i][y0:y1, x0:x1]
        if crop.size == 0:
            continue
        t = cv2.resize(crop, (W, int(W * crop.shape[0] / crop.shape[1])))
        cv2.putText(t, f"f{i}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(t)
if tiles_a and tiles_b:
    hgt = min(t.shape[0] for t in tiles_a + tiles_b)
    sheet = np.vstack([np.hstack([t[:hgt] for t in tiles_a]), np.hstack([t[:hgt] for t in tiles_b])])
    cv2.imwrite(str(out_dir / "strip.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(out_dir / "strip.jpg", "rows: H3 / synced", "frames", len(fa), len(fb))
else:
    print("no face found for the strip")

subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(a), "-i", str(b), "-filter_complex",
                "[0:v]scale=672:384[l];[1:v]scale=672:384[r];[l][r]hstack", "-map", "1:a",
                "-c:v", "libx264", "-crf", "20", "-c:a", "copy", "-shortest", str(out_dir / "compare.mp4")], check=True)
print(out_dir / "compare.mp4", "left = H3 take, right = lip-synced")
