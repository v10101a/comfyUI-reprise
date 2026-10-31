"""Measure lip sync of a generated singing clip against its vocal: mouth opening per frame vs the vocal envelope.

Needs mediapipe (>=0.10, FaceLandmarker task API), opencv, numpy, scipy, soundfile, matplotlib, plus the
face_landmarker.task model (https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task).
These are not in the project venvs; use a throwaway venv.

  python scripts/h3_sync_check.py --video outputs/h3_audio/x/x_mux.mp4 --vocal outputs/h3_audio/x/clip.wav \\
      --model face_landmarker.task [--plot outputs/h3_audio/x/sync.png]

Reports: face-detection rate, Pearson r between mouth opening and vocal RMS at lag 0 and at the best lag in
+-0.5 s (positive lag = mouth late), and the same on the first differences (onsets). For reference, a mouth
that tracks the vocal gives r(level) ~0.5+ near lag 0; a mouth that moves at random gives |r| < 0.2.
"""
import argparse
import json
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import soundfile as sf


def mouth_series(video: Path, model: Path) -> tuple[np.ndarray, np.ndarray, float]:
    opts = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, output_face_blendshapes=True, num_faces=1)
    lm = mp.tasks.vision.FaceLandmarker.create_from_options(opts)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    gap, jaw, i = [], [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        r = lm.detect_for_video(img, int(i * 1000 / fps))
        if r.face_landmarks:
            p = r.face_landmarks[0]
            face_h = abs(p[152].y - p[10].y) or 1.0
            gap.append(abs(p[14].y - p[13].y) / face_h)  # inner-lip gap / face height
            jaw.append(next(b.score for b in r.face_blendshapes[0] if b.category_name == "jawOpen"))
        else:
            gap.append(np.nan)
            jaw.append(np.nan)
        i += 1
    return np.array(gap), np.array(jaw), fps


def vocal_envelope(wav: Path, fps: float, n: int) -> np.ndarray:
    y, sr = sf.read(str(wav), always_2d=True)
    y = y.mean(axis=1)
    hop = sr / fps
    env = np.array([np.sqrt(np.mean(y[int(k * hop):int((k + 1) * hop)] ** 2) + 1e-12) for k in range(n)])
    return 20 * np.log10(env + 1e-6)


def fill(x: np.ndarray) -> np.ndarray:
    idx = np.arange(len(x))
    ok = ~np.isnan(x)
    return np.interp(idx, idx[ok], x[ok]) if ok.any() else np.zeros_like(x)


def lag_corr(a: np.ndarray, b: np.ndarray, max_lag: int) -> list[tuple[int, float]]:
    """r(lag): correlate audio a[t] with mouth b[t+lag]; positive lag = mouth late."""
    out = []
    for lag in range(-max_lag, max_lag + 1):
        x, y = (a[:len(a) - lag], b[lag:]) if lag >= 0 else (a[-lag:], b[:len(b) + lag])
        out.append((lag, float(np.corrcoef(x, y)[0, 1])))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--vocal", type=Path, required=True, help="vocal stem for the same window (not the mix)")
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--plot", type=Path)
    a = p.parse_args()

    gap, jaw, fps = mouth_series(a.video, a.model)
    det = float(np.mean(~np.isnan(gap)))
    mouth = fill(jaw)
    env = vocal_envelope(a.vocal, fps, len(mouth))
    ml = int(round(0.5 * fps))
    lvl = lag_corr(env, mouth, ml)
    dif = lag_corr(np.diff(env), np.diff(mouth), ml)
    best_l = max(lvl, key=lambda t: t[1])
    best_d = max(dif, key=lambda t: t[1])
    rep = {
        "video": str(a.video), "frames": len(mouth), "fps": fps, "face_detect_rate": round(det, 3),
        "r_level_lag0": round(dict(lvl)[0], 3), "r_level_best": round(best_l[1], 3),
        "best_lag_ms_level": round(best_l[0] * 1000 / fps), "r_onset_lag0": round(dict(dif)[0], 3),
        "r_onset_best": round(best_d[1], 3), "best_lag_ms_onset": round(best_d[0] * 1000 / fps),
        "r_level_by_lag_ms": {round(l * 1000 / fps): round(r, 3) for l, r in lvl},
    }
    print(json.dumps({k: v for k, v in rep.items() if k != "r_level_by_lag_ms"}, indent=2))
    out_json = a.plot.with_suffix(".json") if a.plot else a.video.with_name("sync.json")
    out_json.write_text(json.dumps(rep, indent=2))
    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        t = np.arange(len(mouth)) / fps
        z = lambda x: (x - np.nanmean(x)) / (np.nanstd(x) + 1e-9)  # noqa: E731
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.plot(t, z(env), label="vocal RMS (dB)", lw=1.2)
        ax.plot(t, z(mouth), label="mouth jawOpen", lw=1.2)
        ax.set_xlabel("s")
        ax.set_title(f"{a.video.name}  r0={rep['r_level_lag0']}  best r={rep['r_level_best']} @ {rep['best_lag_ms_level']} ms")
        ax.legend(loc="upper right", fontsize=8)
        fig.tight_layout()
        fig.savefig(a.plot, dpi=110)


if __name__ == "__main__":
    main()
