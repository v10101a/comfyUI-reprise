"""AudioBeatMarkers — beat-track a ComfyUI AUDIO and return beat times as JSON."""
import json

import librosa
import numpy as np


class AudioBeatMarkers:
    """Beat-track a ComfyUI AUDIO and return beat times as a JSON string.

    AUDIO in ComfyUI is a dict: {"waveform": tensor[B, C, T], "sample_rate": int}
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "tightness": ("FLOAT", {"default": 100.0, "min": 1.0, "max": 1000.0, "step": 1.0}),
            }
        }

    RETURN_TYPES = ("STRING", "FLOAT", "INT")
    RETURN_NAMES = ("beats_json", "bpm", "beat_count")
    FUNCTION = "run"
    CATEGORY = "Reprise/audio"

    def run(self, audio, tightness):
        wav = audio["waveform"][0]            # first item in batch -> [C, T]
        sr = int(audio["sample_rate"])
        mono = wav.mean(dim=0).cpu().numpy().astype(np.float32)
        tempo, frames = librosa.beat.beat_track(y=mono, sr=sr, tightness=tightness)
        times = librosa.frames_to_time(frames, sr=sr)
        bpm = float(np.atleast_1d(tempo)[0])
        return (json.dumps([round(float(t), 4) for t in times]), bpm, int(len(times)))


NODE_CLASS_MAPPINGS = {"AudioBeatMarkers": AudioBeatMarkers}
NODE_DISPLAY_NAME_MAPPINGS = {"AudioBeatMarkers": "Audio → Beat Markers (Reprise)"}


# ---- TypesetBeatGrid -------------------------------------------------------------------------

def beat_grid(mono: np.ndarray, sr: int, beats_per_bar: int = 4, section_seconds: float = 8.0,
              hop: int = 512) -> dict:
    """Beats, downbeats and coarse sections for cutting cards/words on the music.

    - beats: librosa dynamic-programming beat tracker on the onset envelope.
    - downbeats: assume `beats_per_bar`; pick the bar phase whose beats carry the most low-frequency
      onset energy (kick/bass hits land on the one), a cheap, deterministic heuristic.
    - sections: agglomerative segmentation of beat-synchronous chroma+MFCC into ~duration/section_seconds
      segments, boundaries snapped to downbeats; label = A/B/C… by feature similarity.
    """
    mono = np.asarray(mono, dtype=np.float32)
    duration = float(len(mono) / sr)
    onset = librosa.onset.onset_strength(y=mono, sr=sr, hop_length=hop)
    tempo, frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=hop)
    bpm = float(np.atleast_1d(tempo)[0])
    beats = librosa.frames_to_time(frames, sr=sr, hop_length=hop)
    out = {"duration": round(duration, 3), "bpm": round(bpm, 2), "beatsPerBar": beats_per_bar,
           "beats": [round(float(t), 3) for t in beats], "downbeats": [], "sections": []}
    if len(frames) < beats_per_bar:
        out["sections"] = [{"start": 0.0, "end": round(duration, 3), "label": "A"}]
        return out
    low = librosa.onset.onset_strength(y=mono, sr=sr, hop_length=hop, fmax=200.0, n_mels=32)
    low = low[: len(onset)]
    strength = [float(np.mean([low[min(f, len(low) - 1)] for f in frames[p::beats_per_bar]])) for p in range(beats_per_bar)]
    phase = int(np.argmax(strength))
    down = beats[phase::beats_per_bar]
    out["downbeats"] = [round(float(t), 3) for t in down]
    out["downbeatPhase"] = phase

    k = int(max(1, min(len(frames) // beats_per_bar, round(duration / section_seconds))))
    chroma = librosa.feature.chroma_cqt(y=mono, sr=sr, hop_length=hop)
    mfcc = librosa.feature.mfcc(y=mono, sr=sr, hop_length=hop, n_mfcc=13)
    feat = np.vstack([librosa.util.normalize(chroma, axis=0), librosa.util.normalize(mfcc, axis=1)])
    sync = librosa.util.sync(feat, frames, aggregate=np.median)
    if k > 1 and sync.shape[1] > k:
        bounds_beats = librosa.segment.agglomerative(sync, k)
    else:
        bounds_beats = np.array([0])
    edges = [0.0] + [float(beats[max(0, b - 1)]) if b > 0 else 0.0 for b in bounds_beats[1:]] + [duration]
    # snap interior boundaries to the nearest downbeat
    snapped = [0.0]
    for e in edges[1:-1]:
        t = float(down[np.argmin(np.abs(down - e))]) if len(down) else e
        if t - snapped[-1] > 1.0:
            snapped.append(t)
    snapped.append(duration)
    # label segments by mean feature similarity (greedy clustering, cosine > 0.9 → same letter)
    times = librosa.frames_to_time(np.arange(feat.shape[1]), sr=sr, hop_length=hop)
    reps, labels = [], []
    for a, b in zip(snapped, snapped[1:]):
        sel = (times >= a) & (times < b)
        v = feat[:, sel].mean(axis=1) if sel.any() else feat.mean(axis=1)
        v = v / (np.linalg.norm(v) + 1e-9)
        sims = [float(v @ r) for r in reps]
        if sims and max(sims) > 0.9:
            labels.append(chr(65 + int(np.argmax(sims))))
        else:
            reps.append(v)
            labels.append(chr(65 + len(reps) - 1))
    out["sections"] = [{"start": round(a, 3), "end": round(b, 3), "label": l} for a, b, l in zip(snapped, snapped[1:], labels)]
    return out


def beat_grid_image(mono: np.ndarray, sr: int, grid: dict, width: int = 1280, height: int = 240) -> np.ndarray:
    """Waveform with sections (tinted bands), beats (thin) and downbeats (thick) — RGB uint8."""
    img = np.full((height, width, 3), 24, np.uint8)
    dur = max(grid["duration"], 1e-6)
    palette = [(60, 90, 160), (150, 70, 90), (70, 140, 90), (150, 130, 60), (110, 80, 150), (60, 140, 150)]
    for s in grid["sections"]:
        x0, x1 = int(s["start"] / dur * width), int(s["end"] / dur * width)
        img[:, x0:x1] = np.array(palette[(ord(s["label"]) - 65) % len(palette)]) // 2
    n = len(mono)
    cols = np.array_split(np.abs(mono), width) if n >= width else [np.abs(mono)] * width
    peak = max(float(np.abs(mono).max()), 1e-6)
    mid = height // 2
    for x, c in enumerate(cols):
        a = int((float(c.max()) if len(c) else 0) / peak * (height * 0.42))
        img[mid - a: mid + a + 1, x] = (200, 200, 200)
    for t in grid["beats"]:
        x = min(width - 1, int(t / dur * width)); img[:, x] = (90, 90, 90)
    for t in grid["downbeats"]:
        x = min(width - 1, int(t / dur * width)); img[:, max(0, x - 1):x + 2] = (255, 210, 0)
    import cv2
    for s in grid["sections"]:
        x = int(s["start"] / dur * width)
        img[:, x:x + 3] = (255, 255, 255)
        cv2.putText(img, s["label"], (x + 8, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    return img


class TypesetBeatGrid:
    """AUDIO → {duration, bpm, beatsPerBar, beats, downbeats, downbeatPhase, sections:[{start,end,label}]}
    (seconds), plus a waveform preview. Use it to cut cards/words on the beat and change looks per section."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"audio": ("AUDIO",)},
                "optional": {
                    "beats_per_bar": ("INT", {"default": 4, "min": 1, "max": 12}),
                    "section_seconds": ("FLOAT", {"default": 8.0, "min": 1.0, "max": 120.0, "step": 0.5,
                                                  "tooltip": "Target average section length."}),
                }}

    RETURN_TYPES = ("STRING", "FLOAT", "IMAGE")
    RETURN_NAMES = ("beats_json", "bpm", "preview")
    FUNCTION = "run"
    CATEGORY = "Reprise/audio"

    def run(self, audio, beats_per_bar=4, section_seconds=8.0):
        import torch
        wav = audio["waveform"][0]
        sr = int(audio["sample_rate"])
        mono = wav.float().mean(dim=0).cpu().numpy().astype(np.float32)
        if sr > 22050:  # beat tracking does not need more; 2× faster
            mono = librosa.resample(mono, orig_sr=sr, target_sr=22050)
            sr = 22050
        grid = beat_grid(mono, sr, beats_per_bar, section_seconds)
        prev = torch.from_numpy(beat_grid_image(mono, sr, grid)[None].astype(np.float32) / 255.0)
        return (json.dumps(grid), grid["bpm"], prev)


NODE_CLASS_MAPPINGS["TypesetBeatGrid"] = TypesetBeatGrid
NODE_DISPLAY_NAME_MAPPINGS["TypesetBeatGrid"] = "Beat Grid — beats, downbeats, sections (Reprise)"
