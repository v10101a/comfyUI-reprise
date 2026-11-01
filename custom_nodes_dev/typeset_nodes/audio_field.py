"""TypesetAudioField: the full mix's low band (kick + bass) → a smooth 0..1 pulse per video frame (Typeset "audio" field).

STFT of the mix, energy in [band_low, band_high] Hz, in dB, normalised by percentiles (robust to a few loud hits),
then an instant-attack / slow-release envelope, peak-held per video frame, so the type hits ON the kick (never after)
and falls back smoothly.
The studio maps it onto the size of each word. Same file slot as TypesetVoiceField (voice.json readers tell the
two apart by "kind": "bass"); no separation, no model weights. band_doc is numpy-only (the API's fallback imports it).
"""
import json

import numpy as np

AUDIO_SR = 22050
OVERSAMPLE = 8  # STFT hops per video frame; the envelope runs at this rate, then each frame keeps its peak


def band_doc(y: np.ndarray, sr: int, fps: float, duration: float | None = None, band=(40.0, 140.0),
             n_fft: int = 1024, attack_ms: float = 0.0, release_ms: float = 250.0, lead_frames: float = 0.5,
             lo_pct: float = 20.0, hi_pct: float = 97.0) -> dict:
    """y: mono mix at sr → {kind: 'bass', fps, frames, band, level[0..1]} with one value per video frame.

    Timing (so the type hits ON the kick, never after it): frame f is on screen for song time
    [t0 + f/fps, t0 + (f+1)/fps). Each STFT window is centred on its hop's time (no half-window or hop delay),
    the envelope rises instantly (attack_ms 0) and falls over release_ms, and level[f] is the envelope's peak
    within frame f's interval shifted lead_frames earlier (a small lead reads as "on the beat" on screen)."""
    y = np.asarray(y, np.float32)
    n_frames = int(round((duration if duration else len(y) / sr) * fps))
    lo_hz, hi_hz = float(min(band)), float(max(band))
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)
    bins = np.where((freqs >= lo_hz) & (freqs <= hi_hz))[0]
    if not len(bins):  # band narrower than a bin: take the nearest one
        bins = np.array([int(np.argmin(np.abs(freqs - (lo_hz + hi_hz) / 2)))])
    win = np.hanning(n_fft).astype(np.float32)
    pad = np.pad(y, (n_fft, n_fft))
    dt = 1 / (fps * OVERSAMPLE)
    lead = int(round(lead_frames * OVERSAMPLE))
    n_hops = max(1, (n_frames + 1) * OVERSAMPLE + max(lead, 0))
    centres = np.arange(n_hops) * dt  # hop i is centred exactly on song second t0 + i*dt
    starts = np.clip(np.round(centres * sr).astype(int) - n_fft // 2 + n_fft, 0, len(pad) - n_fft)
    energy = np.empty(n_hops, np.float64)
    for c in range(0, n_hops, 512):  # chunked: a long song is thousands of windows
        idx = starts[c:c + 512, None] + np.arange(n_fft)[None]
        spec = np.fft.rfft(pad[idx] * win, axis=1)
        energy[c:c + 512] = (np.abs(spec[:, bins]) ** 2).sum(1)
    db = 10 * np.log10(np.maximum(energy, 1e-10))
    heard = db[:n_frames * OVERSAMPLE] if n_frames else db
    audible = heard[heard > heard.max() - 80]  # digital silence doesn't set the floor
    lo, hi = np.percentile(audible, lo_pct), np.percentile(audible, hi_pct)
    x = np.clip((db - lo) / max(hi - lo, 1e-3), 0, 1)
    # Envelope: instant (or attack_ms) rise, release_ms fall.
    a_up = 1.0 if attack_ms <= 0 else 1 - np.exp(-dt / (attack_ms / 1000))
    a_dn = 1 - np.exp(-dt / max(release_ms / 1000, 1e-4))
    env = np.empty_like(x)
    e = float(x[0]) if len(x) else 0.0
    for i, v in enumerate(x):
        e += (v - e) * (a_up if v > e else a_dn)
        env[i] = e
    level = []
    for f in range(n_frames):  # peak hold within the (lead-shifted) frame
        a = min(max(0, f * OVERSAMPLE + lead), len(env) - 1)
        level.append(float(env[a:a + OVERSAMPLE].max()))
    return {"kind": "bass", "fps": fps, "frames": n_frames, "band": [lo_hz, hi_hz], "attackMs": attack_ms,
            "releaseMs": release_ms, "leadFrames": lead_frames, "db": [round(float(lo), 2), round(float(hi), 2)],
            "level": [round(v, 3) for v in level]}


def band_preview(doc: dict, y: np.ndarray | None = None, sr: int = AUDIO_SR, width: int = 1200, height: int = 260) -> np.ndarray:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, height), (27, 31, 17))
    d = ImageDraw.Draw(img)
    n = max(1, doc["frames"])
    if y is not None and len(y):
        span = n / doc["fps"]
        for x in range(width):
            a, b = int(x / width * span * sr), int((x + 1) / width * span * sr)
            seg = y[a:max(a + 1, b)]
            if len(seg):
                h = float(np.abs(seg).max()) * height * .45
                d.line([(x, height / 2 - h), (x, height / 2 + h)], fill=(59, 64, 40))
    pts = [(int(f / n * width), height - 4 - (v or 0) * (height - 30)) for f, v in enumerate(doc["level"])]
    if len(pts) > 1:
        d.line(pts, fill=(216, 255, 98), width=2)
    d.text((8, 8), f"audio field · {doc['band'][0]:g}-{doc['band'][1]:g} Hz · {doc['frames']} frames @ {doc['fps']:g} fps",
           fill=(199, 199, 199))
    return np.asarray(img)


class TypesetAudioField:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "audio": ("AUDIO", {"tooltip": "The full mix (not a stem)."}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001}),
            "band_low": ("FLOAT", {"default": 40.0, "min": 10.0, "max": 2000.0, "step": 1.0, "tooltip": "Low edge of the band (Hz)."}),
            "band_high": ("FLOAT", {"default": 140.0, "min": 20.0, "max": 8000.0, "step": 1.0, "tooltip": "High edge of the band (Hz). 40-140 = kick + bass."}),
        }, "optional": {
            "attack_ms": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1000.0, "step": 1.0, "tooltip": "0 = instant: the type hits on the kick."}),
            "release_ms": ("FLOAT", {"default": 250.0, "min": 10.0, "max": 3000.0, "step": 5.0, "tooltip": "How long the type takes to settle after a hit."}),
            "lead_frames": ("FLOAT", {"default": 0.5, "min": -2.0, "max": 3.0, "step": 0.25, "tooltip": "Show each hit this many frames early (0.5 = peaks land on the kick's frame, never after)."}),
            "duration": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 36000.0, "step": 0.001, "tooltip": "Seconds to cover (0 = the audio's length)."}),
        }}

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("voice_json", "preview")
    FUNCTION = "run"
    CATEGORY = "typeset/audio"
    DESCRIPTION = "Mix → low-band (kick/bass) energy per frame, smoothed with attack/release: the 'audio' field that pulses the type."

    def run(self, audio, fps, band_low=40.0, band_high=140.0, attack_ms=0.0, release_ms=250.0, lead_frames=0.5, duration=0.0):
        import torch
        from .lyric_align import _audio_tensor, _resample
        wave, sr = _audio_tensor(audio)
        y = _resample(wave.mean(0)[None].float(), sr, AUDIO_SR)[0].numpy()
        doc = band_doc(y, AUDIO_SR, float(fps), duration or None, (band_low, band_high), attack_ms=attack_ms,
                       release_ms=release_ms, lead_frames=lead_frames)
        image = torch.from_numpy(band_preview(doc, y).astype(np.float32) / 255.0)[None]
        return (json.dumps(doc), image)


NODE_CLASS_MAPPINGS = {"TypesetAudioField": TypesetAudioField}
NODE_DISPLAY_NAME_MAPPINGS = {"TypesetAudioField": "Audio Field • low-band pulse (typeset)"}
