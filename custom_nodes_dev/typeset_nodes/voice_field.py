"""TypesetVoiceField: song → how the voice moves, per video frame (Typeset "voice" field).

The studio maps it onto the letters: loudness swells the variable-font weight/width, pitch lifts the baseline
along the melody, vibrato wobbles it, vocal onsets kick. Vocals come from HDemucs (shared with
TypesetAlignLyrics) or from a connected stem.
"""
import json

import numpy as np
import torch

from .lyric_align import SEPARATORS, _audio_tensor, _resample, unload_models

VOICE_SR = 16000
HOP = 160  # 10 ms analysis hop


def voice_doc(stem: np.ndarray, sr: int, fps: float, duration: float | None = None) -> dict:
    """stem: mono float vocal stem at sr → {fps, loud[0..1], pitch[midi|null], vibrato[0..1], onset[0..1]} per frame."""
    import librosa
    y = stem.astype(np.float32)
    n_frames = int(round((duration if duration else len(y) / sr) * fps))
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=HOP, center=True)[0]
    db = 20 * np.log10(np.maximum(rms, 1e-5))
    lo, hi = np.percentile(db, 10), np.percentile(db, 99)
    loud = np.clip((db - lo) / max(hi - lo, 1e-3), 0, 1)
    f0, voiced, _ = librosa.pyin(y, fmin=70, fmax=1100, sr=sr, frame_length=1024, hop_length=HOP)
    midi = np.where(voiced & np.isfinite(f0), librosa.hz_to_midi(np.nan_to_num(f0, nan=1.0)), np.nan)
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    onset = np.clip(onset / max(np.percentile(onset, 99), 1e-6), 0, 1)
    # Vibrato: pitch wobble around a 0.25 s moving average, in semitones, mapped to 0..1 at ±0.6 st.
    k = max(1, int(.25 * sr / HOP))
    filled = np.where(np.isnan(midi), np.nan, midi)
    smooth = np.convolve(np.nan_to_num(filled, nan=0), np.ones(k) / k, "same") / np.maximum(
        np.convolve(~np.isnan(filled), np.ones(k) / k, "same"), 1e-6)
    vib = np.clip(np.abs(np.nan_to_num(filled - smooth, nan=0)) / .6, 0, 1)
    t_hop = np.arange(len(rms)) * HOP / sr

    def per_frame(a, how="mean"):
        out = []
        for f in range(n_frames):
            m = (t_hop >= f / fps) & (t_hop < (f + 1) / fps)
            v = a[: len(t_hop)][m] if m.any() else a[min(len(a) - 1, int(f / fps * sr / HOP)):][:1]
            v = v[~np.isnan(v)] if v.dtype.kind == "f" else v
            out.append(None if not len(v) else float(np.max(v) if how == "max" else np.median(v) if how == "median" else np.mean(v)))
        return out

    r3 = lambda xs: [None if x is None else round(x, 3) for x in xs]
    return {"fps": fps, "frames": n_frames, "loud": r3(per_frame(loud)), "pitch": r3(per_frame(midi, "median")),
            "vibrato": r3(per_frame(vib)), "onset": r3(per_frame(onset[: len(t_hop)], "max"))}


def voice_preview(doc: dict, width: int = 1200, height: int = 260) -> np.ndarray:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, height), (27, 31, 17))
    d = ImageDraw.Draw(img)
    n = max(1, doc["frames"])
    for f in range(doc["frames"]):
        x = int(f / n * width)
        loud = doc["loud"][f] or 0
        d.line([(x, height), (x, height - loud * height * .5)], fill=(59, 64, 40))
        if doc["onset"][f] and doc["onset"][f] > .6:
            d.line([(x, 0), (x, 10)], fill=(200, 200, 255))
    pts = [(int(f / n * width), height - (p - 36) / 48 * height) for f, p in enumerate(doc["pitch"]) if p is not None]
    for x, y in pts:
        d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(178, 162, 205))
    d.text((8, 8), f"voice field · {doc['frames']} frames @ {doc['fps']:g} fps · loudness (olive) · pitch (lavender)", fill=(199, 199, 199))
    return np.asarray(img)


class TypesetVoiceField:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "audio": ("AUDIO",),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001}),
            "separator": (list(SEPARATORS), {"default": "hdemucs", "tooltip": "Vocal separation ('none' = analyse the mix). Ignored when a vocals stem is connected."}),
        }, "optional": {
            "vocals": ("AUDIO", {"tooltip": "An already-separated vocal stem (e.g. TypesetAlignLyrics' vocals output)."}),
            "duration": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 36000.0, "step": 0.001, "tooltip": "Seconds of video to cover (0 = the audio's length)."}),
            "device": (["cpu", "mps"], {"default": "cpu"}),
        }}

    RETURN_TYPES = ("STRING", "IMAGE", "AUDIO")
    RETURN_NAMES = ("voice_json", "preview", "vocals")
    FUNCTION = "run"
    CATEGORY = "Reprise/audio"
    DESCRIPTION = "Vocal stem → per-frame loudness, pitch (pYIN), vibrato and onsets: the 'voice' field that animates the type."

    def run(self, audio, fps, separator="hdemucs", vocals=None, duration=0.0, device="cpu"):
        if device == "mps" and not torch.backends.mps.is_available():
            device = "cpu"
        if vocals is not None:
            wave, sr = _audio_tensor(vocals)
            stem = wave.mean(0)
        else:
            wave, sr = _audio_tensor(audio)
            try:
                stem, sr = SEPARATORS[separator](wave, sr, device)
            finally:
                if separator != "none":
                    unload_models()
        stem16 = _resample(stem[None].float(), sr, VOICE_SR)[0]
        doc = voice_doc(stem16.numpy(), VOICE_SR, float(fps), duration or None)
        image = torch.from_numpy(voice_preview(doc).astype(np.float32) / 255.0)[None]
        return (json.dumps(doc), image, {"waveform": stem16[None, None, :].clone(), "sample_rate": VOICE_SR})


NODE_CLASS_MAPPINGS = {"TypesetVoiceField": TypesetVoiceField}
NODE_DISPLAY_NAME_MAPPINGS = {"TypesetVoiceField": "Voice Field • loudness + pitch (Reprise)"}
