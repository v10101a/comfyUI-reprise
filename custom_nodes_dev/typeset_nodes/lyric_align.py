"""Acoustic forced alignment of KNOWN lyrics to sung vocals (TypesetAlignLyrics).

Pipeline (all local, torchaudio bundles; weights download once to ~/.cache/torch/hub):
  1. vocals   HDEMUCS_HIGH_MUSDB_PLUS separates the vocal stem, in overlapping chunks (bounded memory).
  2. text     lyrics -> per-word CTC tokens: NFKD romanization, lowercase, punctuation stripped, numbers spelled.
  3. align    MMS_FA (wav2vec2 CTC aligner, 20 ms frames) emissions over the stem, chunked, then
              torchaudio.functional.forced_align with a '*' (star) token between lines that absorbs ad-libs,
              backing vocals and anything not in the lyrics.
  4. refine   each word start moves to the nearest vocal-stem onset (band-limited flux peaks) within ±onset_window;
              each end is extended over the sustained note while the stem stays loud (until the next word).
  5. flag     confidence = mean CTC posterior of the word's characters (separated singing scores far lower than
              speech: 0.01-0.5 is normal); `lowConfidence` below min_confidence, when the word had no alignable
              letters (time interpolated), or when it was pinned to the vocal_start edge (no evidence).

Output is the SCHEMA §2 words.json document with source "forced-align". Extra per-word fields (`ctcStart`,
`onsetShift`, `lowConfidence`, `pinned`) are ignored by the server's timeline seeding.
"""
from __future__ import annotations

import json
import math
import re
import threading
import unicodedata

import numpy as np
import torch

from .whisper_words import lyric_lines_of

ALIGN_SR = 16000
SEP_SR = 44100
_MODELS: dict = {}
_LOCK = threading.Lock()


# ---- models -----------------------------------------------------------------------------------------

def _model(name: str, device: str):
    key = (name, device)
    with _LOCK:
        if key not in _MODELS:
            from torchaudio import pipelines
            if name == "hdemucs":
                m = pipelines.HDEMUCS_HIGH_MUSDB_PLUS.get_model()
            else:
                m = pipelines.MMS_FA.get_model(with_star=True)
            _MODELS[key] = m.to(device).eval()
        return _MODELS[key]


def unload_models():
    with _LOCK:
        _MODELS.clear()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()


def _resample(x: torch.Tensor, sr: int, target: int) -> torch.Tensor:
    if sr == target:
        return x
    import torchaudio.functional as AF
    return AF.resample(x, sr, target)


# ---- 1. vocal separation -------------------------------------------------------------------------------

def separate_vocals(wave: torch.Tensor, sr: int, chunk_s: float = 10.0, overlap_s: float = 1.0,
                    device: str = "cpu", progress=None) -> torch.Tensor:
    """wave [C, N] at sr -> mono vocal stem [N'] at SEP_SR. Chunks overlap and cross-fade linearly, so peak
    memory is one chunk of the 4-source output whatever the song length."""
    model = _model("hdemucs", device)
    x = _resample(wave.float(), sr, SEP_SR)
    if x.shape[0] == 1:
        x = x.repeat(2, 1)
    x = x[:2]
    ref = x.mean(0)
    mean, std = ref.mean(), ref.std().clamp_min(1e-8)
    x = (x - mean) / std
    n = x.shape[1]
    chunk, ov = int(chunk_s * SEP_SR), int(overlap_s * SEP_SR)
    vidx = model.sources.index("vocals")
    out = torch.zeros(n)
    weight = torch.zeros(n)
    starts = list(range(0, max(1, n - ov), chunk - ov)) or [0]
    for k, s in enumerate(starts):
        e = min(n, s + chunk)
        seg = x[:, s:e].unsqueeze(0).to(device)
        with torch.inference_mode():
            v = model(seg)[0, vidx].mean(0).float().cpu()
        w = torch.ones(e - s)
        f = min(ov, (e - s) // 2)
        if f > 0:
            ramp = torch.linspace(0, 1, f)
            if s > 0:
                w[:f] = ramp
            if e < n:
                w[-f:] = ramp.flip(0)
        out[s:e] += v * w
        weight[s:e] += w
        del seg, v
        if progress:
            progress(k + 1, len(starts))
        if e >= n:
            break
    return out / weight.clamp_min(1e-6) * std + mean


# ---- 2. lyric normalization ------------------------------------------------------------------------------

_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_ORD = {"1st": "first", "2nd": "second", "3rd": "third", "4th": "fourth", "5th": "fifth", "6th": "sixth",
        "7th": "seventh", "8th": "eighth", "9th": "ninth", "10th": "tenth"}
_SPECIAL = {"ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "đ": "d", "ł": "l", "þ": "th", "ð": "d", "&": " and ",
            "’": "'", "‘": "'", "`": "'", "%": " percent "}


def number_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + number_words(n % 100))
    if n < 1_000_000:
        return number_words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + number_words(n % 1000))
    return " ".join(_ONES[int(d)] for d in str(n))


def normalize_word(tok: str) -> str:
    """One lyric token -> the letters MMS_FA can align ([a-z'] plus spelled numbers, space-separated)."""
    t = tok.lower()
    if t.strip(".,!?;:\"()") in _ORD:
        return _ORD[t.strip(".,!?;:\"()")]
    t = "".join(_SPECIAL.get(c, c) for c in t)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\d+", lambda m: " " + number_words(int(m.group())) + " ", t)
    t = re.sub(r"[^a-z' ]+", " ", t)
    t = re.sub(r"(^|\s)'+|'+(\s|$)", " ", t)  # quote marks, not elisions
    return " ".join(t.split())


def lyric_tokens(lyrics: str):
    """-> (lines, toks) with toks = [(line_idx, display_text, normalized_letters)]."""
    lines = lyric_lines_of(lyrics)
    toks = []
    for li, ln in enumerate(lines):
        for t in ln.split():
            toks.append((li, t, normalize_word(t)))
    return lines, toks


# ---- 3. CTC emissions + forced alignment -------------------------------------------------------------

def emissions(vocals16: torch.Tensor, device: str = "cpu", chunk_s: float = 20.0, ctx_s: float = 2.0,
              progress=None) -> tuple[torch.Tensor, float]:
    """vocals16 [N] at 16 kHz -> (log-probs [T, V], seconds per frame). Chunked with context on both sides;
    only each chunk's centre frames are kept."""
    model = _model("mms", device)
    x = vocals16.float()
    x = (x - x.mean()) / x.std().clamp_min(1e-8)  # MMS expects normalized input
    n = x.shape[0]
    chunk, ctx = int(chunk_s * ALIGN_SR), int(ctx_s * ALIGN_SR)
    parts, s, k = [], 0, 0
    total = max(1, math.ceil(n / chunk))
    hop = 320  # wav2vec2 conv stride: 20 ms
    while s < n:
        e = min(n, s + chunk)
        a, b = max(0, s - ctx), min(n, e + ctx)
        with torch.inference_mode():
            em, _ = model(x[a:b].unsqueeze(0).to(device))
        em = em[0].float().cpu()  # already log-probs; the with_star column is a constant 0 (do not renormalize)
        f0 = round((s - a) / hop)
        f1 = f0 + round((e - s) / hop)
        parts.append(em[f0:min(f1, em.shape[0])])
        s = e
        k += 1
        if progress:
            progress(k, total)
    em = torch.cat(parts)
    return em, n / ALIGN_SR / em.shape[0]


def ctc_align(em: torch.Tensor, toks, use_star: bool = True):
    """Forced alignment of the lyric tokens. Returns per-token (frame_start, frame_end, score) or None for
    tokens without alignable letters; frame_end is exclusive."""
    import torchaudio.functional as AF
    from torchaudio.pipelines import MMS_FA
    d = MMS_FA.get_dict(star="*")
    star = d["*"]
    seq, owner = [], []  # owner[i] = token index of each target, -1 for star
    prev_line = None
    for ti, (li, _disp, norm) in enumerate(toks):
        if use_star and li != prev_line:
            seq.append(star); owner.append(-1)
        prev_line = li
        for part in norm.split():
            for c in part:
                if c in d:
                    seq.append(d[c]); owner.append(ti)
    if use_star:
        seq.append(star); owner.append(-1)
    if not any(o >= 0 for o in owner):
        return [None] * len(toks)
    # CTC needs one frame per target plus a blank between each pair of identical neighbours ("ll", "ee").
    need = len(seq) + sum(1 for a, b in zip(seq, seq[1:]) if a == b)
    if em.shape[0] < need:
        raise ValueError(f"audio too short to align these lyrics: {need} CTC frames needed "
                         f"({len(seq)} characters incl. repeats), {em.shape[0]} available ({em.shape[0] * 0.02:.1f} s)")
    targets = torch.tensor([seq], dtype=torch.int32)
    labels, scores = AF.forced_align(em.unsqueeze(0), targets, blank=0)
    spans = AF.merge_tokens(labels[0], scores[0].exp())
    assert len(spans) == len(seq), (len(spans), len(seq))
    out: list = [None] * len(toks)
    acc: dict[int, list] = {}
    for sp, o in zip(spans, owner):
        if o >= 0:
            acc.setdefault(o, []).append(sp)
    for ti, sps in acc.items():
        n = sum(s.end - s.start for s in sps)
        score = sum(s.score * (s.end - s.start) for s in sps) / max(1, n)
        out[ti] = (sps[0].start, sps[-1].end, float(score))
    return out


# ---- backend registries (swappable) -----------------------------------------------------------------
# A separator: (wave [C,N], sr, device) -> (mono stem tensor, stem_sr).
# An aligner:  (stem16 [N] at 16 kHz, toks, device, span) -> (per-token (start_s, end_s, score) | None, frame_seconds,
#              realign | None) where realign(token_indices, t0, t1) re-aligns a subset inside a window.
#              span = (start_s, end_s | None): words must fall inside it (instrumental intros/outros excluded).
# Register a new backend here and it appears in the node's combo; nothing else changes.

def _sep_hdemucs(wave, sr, device):
    return separate_vocals(wave, sr, device=device), SEP_SR


def _sep_none(wave, sr, device):
    return wave.float().mean(0), sr


def _align_mms(stem16, toks, device, span=(0.0, None)):
    em, spf = emissions(stem16, device=device)
    f0 = max(0, int(round(span[0] / spf)))
    f1 = em.shape[0] if not span[1] else min(em.shape[0], int(round(span[1] / spf)))
    if f0 > 0 or f1 < em.shape[0]:
        # outside the span only blank/star may be emitted (the star column is a constant 0 log-prob)
        em[:f0, 1:em.shape[1] - 1] = -1e4
        em[f1:, 1:em.shape[1] - 1] = -1e4
    al = ctc_align(em, toks)

    def realign(idx, t0, t1):
        """Align only toks[idx] inside [t0, t1] seconds (stars around them absorb everything else)."""
        e = em.clone()
        a, b = max(0, int(t0 / spf)), min(e.shape[0], int(t1 / spf))
        e[:a, 1:e.shape[1] - 1] = -1e4
        e[b:, 1:e.shape[1] - 1] = -1e4
        r = ctc_align(e, [toks[i] for i in idx])
        return [None if x is None else (x[0] * spf, x[1] * spf, x[2]) for x in r]

    return [None if a is None else (a[0] * spf, a[1] * spf, a[2]) for a in al], spf, realign


SEPARATORS = {"hdemucs": _sep_hdemucs, "none": _sep_none}
ALIGNERS = {"mms_fa": _align_mms}


# ---- 4. onset refinement ---------------------------------------------------------------------------------

ENV_HOP = 160  # 10 ms at 16 kHz


def onset_envelope(vocals16: torch.Tensor):
    """Vocal onset strength and frame RMS of the stem, both at 10 ms hops. The flux is band-limited to
    150-4000 Hz (voice formants; separation bleed is mostly drums/bass outside it) and median-aggregated over
    bins, so a word onset (many harmonics rising together) beats a hi-hat. Measured on the demo songs against
    pYIN voiced entries and ear-confirmed hook times, this beat broadband flux (mean error 40 vs 68 ms)."""
    import librosa
    y = vocals16.cpu().numpy().astype(np.float32)
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=ENV_HOP))
    f = librosa.fft_frequencies(sr=ALIGN_SR, n_fft=1024)
    band = (f > 150) & (f < 4000)
    env = librosa.onset.onset_strength(S=librosa.amplitude_to_db(S[band], ref=np.max), sr=ALIGN_SR,
                                       hop_length=ENV_HOP, lag=2, max_size=3, aggregate=np.median)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=ENV_HOP, center=True)[0]
    return env, rms


def onset_times(env: np.ndarray) -> np.ndarray:
    import librosa
    fr = librosa.onset.onset_detect(onset_envelope=env, sr=ALIGN_SR, hop_length=ENV_HOP, units="frames",
                                    backtrack=False, pre_max=3, post_max=3, pre_avg=10, post_avg=10,
                                    delta=0.08, wait=8)  # librosa normalizes env to [0, 1]
    return fr * ENV_HOP / ALIGN_SR


def nearest(onsets: np.ndarray, t: float) -> float:
    if len(onsets) == 0:
        return math.inf
    i = int(np.searchsorted(onsets, t))
    c = [onsets[j] for j in (i - 1, i) if 0 <= j < len(onsets)]
    return min(c, key=lambda o: abs(o - t)) - t


# ---- top level --------------------------------------------------------------------------------------------

def align_lyrics(wave: torch.Tensor, sr: int, lyrics: str, *, vocals: torch.Tensor | None = None,
                 vocals_sr: int | None = None, separator: str = "hdemucs", aligner: str = "mms_fa",
                 device: str = "cpu", onset_window_ms: float = 50.0, min_confidence: float = 0.05,
                 vocal_start: float = 0.0, vocal_end: float = 0.0, word_cap: float = 2.5, progress=None):
    """wave [C, N]. Returns (doc, stem16 [N16] tensor, extra) where extra holds envelope/onsets for previews."""
    lines, toks = lyric_tokens(lyrics)
    if not toks:
        raise ValueError("lyrics are empty (section tags like [chorus] are ignored)")
    say = progress or (lambda *_: None)
    if vocals is not None:
        stem = vocals.float().mean(0) if vocals.ndim == 2 else vocals.float()
        stem_sr, separator = int(vocals_sr or sr), "provided"
    else:
        say(f"separating vocals ({separator})")
        stem, stem_sr = SEPARATORS[separator](wave, sr, device)
    stem16 = _resample(stem, stem_sr, ALIGN_SR).contiguous()
    say(f"forced alignment ({aligner})")
    res = ALIGNERS[aligner](stem16, toks, device, (max(0.0, vocal_start), vocal_end if vocal_end > vocal_start else None))
    al, spf, realign = (res + (None,))[:3]
    env, rms = onset_envelope(stem16)
    ons = onset_times(env)
    win = onset_window_ms / 1000.0
    words = []
    for ti, ((li, disp, _norm), a) in enumerate(zip(toks, al)):
        if a is None:
            words.append({"text": disp, "start": None, "end": None, "confidence": 0.0, "lineId": f"l{li}",
                          "lowConfidence": True})
            continue
        s, e = a[0], a[1]
        words.append({"text": disp, "start": s, "end": e, "confidence": a[2], "lineId": f"l{li}", "ctcStart": s})
    _interpolate_missing(words)
    if realign is not None:
        say("re-anchoring over-long lines")
        _reanchor_lines(words, toks, quiet_runs(rms), realign, word_cap)
    # A word stuck on the span edge has no acoustic evidence (CTC just put it as early as allowed): move it to
    # the first vocal onset inside its own span and flag it.
    if vocal_start > 0:
        for i, w in enumerate(words):
            if w.get("ctcStart") is not None and abs(w["ctcStart"] - vocal_start) < 0.06:
                later = [o for o in ons if vocal_start + 0.06 < o < vocal_start + 1.5]
                if later:
                    w["start"] = float(later[0])
                    w["end"] = max(w["end"], w["start"] + 0.1)
                w["pinned"] = True
                w["lowConfidence"] = True
                # words that now start before it move to the next onset after it (also unproven -> flagged)
                for v in words[i + 1:]:
                    if v["start"] > w["start"] + 0.05:
                        break
                    nxt = [o for o in ons if w["start"] + 0.05 < o < max(v["end"], w["start"] + 1.0)]
                    v["start"] = float(nxt[0]) if nxt else w["start"] + 0.1
                    v["end"] = max(v["end"], v["start"] + 0.1)
                    v["pinned"] = True
                    v["lowConfidence"] = True
                    w = v
    # onset snap (bounded by neighbours so order never flips)
    for i, w in enumerate(words):
        if w.get("ctcStart") is None or w.get("pinned"):
            w["onsetShift"] = None
            continue
        d = nearest(ons, w["start"])
        lo = words[i - 1]["start"] + 0.03 if i > 0 else 0.0
        if abs(d) <= win and w["start"] + d > lo and w["start"] + d < w["end"] - 0.02:
            w["start"] += d
            w["onsetShift"] = round(d, 3)
        else:
            w["onsetShift"] = None
    # ends: sustained notes keep the word on while the stem stays loud, up to the next word
    for i, w in enumerate(words):
        nxt = words[i + 1]["start"] if i + 1 < len(words) else len(stem16) / ALIGN_SR
        f0, f1 = int(w["start"] * 100), int(w["end"] * 100)
        peak = float(rms[f0:max(f0 + 1, f1)].max()) if f1 > f0 and f0 < len(rms) else 0.0
        f = f1
        while f < len(rms) and f / 100 < nxt and rms[f] > 0.3 * peak:
            f += 1
        w["end"] = max(w["end"], min(nxt, f / 100))
        w["end"] = min(w["end"], nxt) if nxt > w["start"] + 0.05 else w["start"] + 0.05
        w["end"] = min(w["end"], w["start"] + word_cap)  # a held word never runs on into an instrumental tail
        w["lowConfidence"] = bool(w.get("lowConfidence") or w["confidence"] < min_confidence)
    for w in words:
        for k in ("start", "end", "confidence", "ctcStart"):
            if w.get(k) is not None:
                w[k] = round(float(w[k]), 3)
    out_lines = []
    for li, ln in enumerate(lines):
        ws = [w for w in words if w["lineId"] == f"l{li}"]
        if ws:
            out_lines.append({"id": f"l{li}", "text": ln, "start": ws[0]["start"], "end": ws[-1]["end"]})
    doc = {"source": "forced-align", "model": f"{aligner}+{separator}",
           "language": "und", "words": words, "lines": out_lines,
           "stats": {"words": len(words), "lowConfidence": sum(w["lowConfidence"] for w in words),
                     "snapped": sum(1 for w in words if w.get("onsetShift") is not None),
                     "reanchored": sum(1 for w in words if w.get("reanchored")),
                     "onsetWindowMs": onset_window_ms, "frameSeconds": round(spf, 5),
                     "vocalStart": vocal_start, "vocalEnd": vocal_end}}
    return doc, stem16, {"env": env, "rms": rms, "onsets": ons}


def quiet_runs(rms: np.ndarray, min_s: float = 0.3, rel: float = 0.1):
    """Stretches (seconds) where the vocal stem is quiet: RMS below rel x its 95th percentile for >= min_s.
    Real instrumental gaps; a sung line never spans one."""
    q = rms < rel * float(np.percentile(rms, 95))
    runs, i = [], 0
    while i < len(q):
        if q[i]:
            j = i
            while j < len(q) and q[j]:
                j += 1
            if (j - i) / 100 >= min_s:
                runs.append((i / 100, j / 100))
            i = j
        else:
            i += 1
    return runs


def _reanchor_lines(words, toks, runs, realign, cap: float = 2.5):
    """Duration cap with automatic windows. One global CTC pass can drop a line into a stretch with stronger
    letter evidence (intro bleed, an echo of another line) and leave the voice that really sings it to blanks.
    The tell: the line's last word would have to hold > cap seconds, with no quiet gap, before the next line
    starts. Such a line is re-aligned in a window that ends where the next line starts and is at most
    cap + 0.5 s/extra word long. If the line's first word then sits on the window edge (no evidence there), the
    edge moves inward 0.2 s at a time until the placement stops depending on it. Processed from the last line
    backwards so each window ends on a settled line."""
    line_of = [li for li, _, _ in toks]
    for li in sorted(set(line_of), reverse=True):
        idx = [i for i, l in enumerate(line_of) if l == li]
        j = idx[-1] + 1
        if j >= len(words) or any(words[i].get("ctcStart") is None for i in idx):
            continue
        last, nstart = idx[-1], words[j]["start"]
        if nstart - words[last]["start"] <= cap or any(a < nstart and b > words[last]["start"] for a, b in runs):
            continue
        t0 = max(0.0, nstart - cap - 0.5 * (len(idx) - 1))
        r = None
        for _ in range(15):
            r = realign(idx, t0, nstart)
            if r[0] is None or r[0][0] - t0 > 0.06 or t0 >= nstart - 0.5 * len(idx):
                break
            t0 += 0.2
        if not r or r[0] is None:
            continue
        for i, x in zip(idx, r):
            if x is not None:
                words[i].update(start=x[0], end=x[1], confidence=x[2], ctcStart=x[0], reanchored=True)


def _interpolate_missing(words):
    n = len(words)
    i = 0
    while i < n:
        if words[i]["start"] is not None:
            i += 1
            continue
        j = i
        while j < n and words[j]["start"] is None:
            j += 1
        lo = words[i - 1]["end"] if i > 0 else max(0.0, (words[j]["start"] if j < n else 0.0) - 0.3 * (j - i))
        hi = words[j]["start"] if j < n else lo + 0.3 * (j - i)
        step = max(0.05, (hi - lo) / (j - i))
        for k in range(i, j):
            words[k]["start"], words[k]["end"] = lo + (k - i) * step, lo + (k - i + 1) * step
        i = j


# ---- preview -------------------------------------------------------------------------------------------

_CMAP = np.array([[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99], [212, 72, 66], [245, 125, 21],
                  [250, 193, 39], [252, 255, 164]], dtype=np.float32)


def _colormap(v: np.ndarray) -> np.ndarray:
    x = np.clip(v, 0, 1) * (len(_CMAP) - 1)
    i = np.minimum(x.astype(int), len(_CMAP) - 2)
    f = (x - i)[..., None]
    return (_CMAP[i] * (1 - f) + _CMAP[i + 1] * f).astype(np.uint8)


def render_preview(stem16: torch.Tensor, rows: list[tuple[str, list[dict], tuple]], *, onsets=None,
                   t0: float = 0.0, t1: float | None = None, px_per_s: int = 120, title: str = ""):
    """PIL image: stem waveform, mel spectrogram, onset ticks, then one row of word boxes per (label, words, rgb)."""
    from PIL import Image, ImageDraw, ImageFont
    import torchaudio
    dur = len(stem16) / ALIGN_SR
    t1 = dur if t1 is None else min(t1, dur)
    W = max(400, int((t1 - t0) * px_per_s)) + 90
    L = 90
    wave_h, spec_h, row_h = 110, 200, 46
    H = 26 + wave_h + spec_h + row_h * len(rows) + 30
    img = Image.new("RGB", (W, H), (14, 15, 18))
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
    except Exception:
        font = ImageFont.load_default()
    X = lambda t: L + (t - t0) * px_per_s
    seg = stem16[int(t0 * ALIGN_SR):int(t1 * ALIGN_SR)].cpu().numpy()
    y0 = 26
    dr.text((6, 6), title or "vocal stem · mel spectrogram · word boxes", fill=(220, 220, 220), font=font)
    # waveform (min/max per pixel column)
    cols = W - L
    if len(seg):
        per = max(1, len(seg) // cols)
        m = seg[:per * (len(seg) // per)].reshape(-1, per)
        mx, mn = m.max(1), m.min(1)
        sc = (wave_h / 2 - 4) / max(1e-6, float(np.abs(seg).max()))
        mid = y0 + wave_h / 2
        for k in range(min(cols, len(mx))):
            dr.line([(L + k, mid - mx[k] * sc), (L + k, mid - mn[k] * sc)], fill=(120, 200, 255))
    dr.text((6, y0 + 4), "vocals", fill=(160, 160, 160), font=font)
    # spectrogram
    ys = y0 + wave_h
    if len(seg) > 2048:
        mel = torchaudio.transforms.MelSpectrogram(ALIGN_SR, n_fft=1024, hop_length=160, n_mels=96, f_max=8000)(
            torch.from_numpy(seg.copy()))
        db = 10 * torch.log10(mel.clamp_min(1e-10))
        db = ((db - (db.max() - 70)) / 70).clamp(0, 1).numpy()[::-1]
        sp = Image.fromarray(_colormap(db)).resize((cols, spec_h), Image.BILINEAR)
        img.paste(sp, (L, ys))
    dr.text((6, ys + 4), "mel", fill=(160, 160, 160), font=font)
    if onsets is not None:
        for o in onsets:
            if t0 <= o <= t1:
                dr.line([(X(o), y0), (X(o), ys + spec_h)], fill=(90, 255, 140), width=1)
    # rows of word boxes
    yr = ys + spec_h + 4
    for label, ws, rgb in rows:
        dr.text((6, yr + 14), label, fill=rgb, font=font)
        for w in ws:
            if w["end"] < t0 or w["start"] > t1:
                continue
            a, b = X(max(t0, w["start"])), X(min(t1, w["end"]))
            fill = tuple(int(c * (0.35 if w.get("lowConfidence") else 0.6)) for c in rgb)
            dr.rectangle([a, yr, max(a + 2, b), yr + row_h - 8], fill=fill, outline=rgb)
            dr.line([(a, y0), (a, ys + spec_h)], fill=rgb, width=1)
            dr.text((a + 3, yr + 3), w["text"], fill=(255, 255, 255), font=font)
        yr += row_h
    # time axis
    for s in range(int(math.ceil(t0)), int(t1) + 1):
        dr.line([(X(s), yr), (X(s), yr + 6)], fill=(180, 180, 180))
        dr.text((X(s) + 2, yr + 6), f"{s}s", fill=(180, 180, 180), font=font)
    return img


# ---- ComfyUI node ---------------------------------------------------------------------------------------

def _audio_tensor(audio):
    wav = audio["waveform"]
    if wav.ndim == 3:
        wav = wav[0]
    return wav.float().cpu(), int(audio["sample_rate"])


class TypesetAlignLyrics:
    """Known lyrics + sung audio -> per-word start/end by acoustic forced alignment (not ASR)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "lyrics": ("STRING", {"default": "", "multiline": True,
                                      "tooltip": "Lyrics as sung, one line per lyric line. [verse]/[chorus] tags are ignored."}),
                "separator": (list(SEPARATORS), {"default": "hdemucs", "tooltip": "Vocal separation backend ('none' = align the mix directly). Ignored when a vocals stem is connected."}),
                "aligner": (list(ALIGNERS), {"default": "mms_fa", "tooltip": "Forced-alignment backend (mms_fa = torchaudio MMS CTC aligner)."}),
                "onset_window_ms": ("FLOAT", {"default": 50.0, "min": 0.0, "max": 250.0, "step": 5.0,
                                              "tooltip": "Snap each word start to the nearest vocal onset within ± this window."}),
                "min_confidence": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.05,
                                             "tooltip": "Words whose mean CTC posterior is below this are flagged lowConfidence."}),
                "vocal_start": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 36000.0, "step": 0.1,
                                          "tooltip": "Seconds: singing starts at or after this. Use it to keep an instrumental intro's bleed from attracting the first line."}),
                "vocal_end": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 36000.0, "step": 0.1,
                                        "tooltip": "Seconds: singing ends by this (0 = end of audio)."}),
                "device": (["cpu", "mps"], {"default": "cpu", "tooltip": "cpu is the safe default; mps is faster where supported."}),
                "unload_models": ("BOOLEAN", {"default": True, "tooltip": "Free HDemucs/MMS weights after the run (keeps ComfyUI memory low)."}),
            },
            "optional": {
                "vocals": ("AUDIO", {"tooltip": "An already-separated vocal stem; skips HDemucs."}),
            },
        }

    RETURN_TYPES = ("STRING", "IMAGE", "AUDIO", "INT")
    RETURN_NAMES = ("words_json", "preview", "vocals", "word_count")
    FUNCTION = "run"
    CATEGORY = "Reprise/audio"
    DESCRIPTION = ("Forced alignment of known lyrics to singing: HDemucs vocal stem -> MMS_FA CTC alignment -> "
                   "onset refinement. Outputs SCHEMA words.json, a stem/spectrogram preview with word boxes, and the stem.")

    def run(self, audio, lyrics, separator="hdemucs", aligner="mms_fa", onset_window_ms=50.0, min_confidence=0.05,
            vocal_start=0.0, vocal_end=0.0, device="cpu", unload_models=True, vocals=None):
        if device == "mps" and not torch.backends.mps.is_available():
            device = "cpu"
        wave, sr = _audio_tensor(audio)
        v, vsr = (_audio_tensor(vocals) if vocals is not None else (None, None))
        pbar = None
        try:
            import comfy.utils
            pbar = comfy.utils.ProgressBar(4)
        except Exception:
            pass
        step = [0]
        def progress(_msg):
            step[0] += 1
            if pbar:
                pbar.update_absolute(min(step[0], 4), 4)
        try:
            doc, stem16, extra = align_lyrics(wave, sr, lyrics, vocals=v, vocals_sr=vsr, separator=separator, aligner=aligner,
                                              device=device, onset_window_ms=onset_window_ms,
                                              min_confidence=min_confidence, vocal_start=vocal_start,
                                              vocal_end=vocal_end, progress=progress)
        finally:
            if unload_models:
                unload_models_fn()
        img = render_preview(stem16, [("aligned", doc["words"], (255, 120, 200))], onsets=extra["onsets"],
                             px_per_s=80, title=f"Reprise · Align Lyrics · {len(doc['words'])} words · "
                                                f"{doc['stats']['lowConfidence']} low-confidence")
        image = torch.from_numpy(np.asarray(img).astype(np.float32) / 255.0)[None]
        stem_audio = {"waveform": stem16[None, None, :].clone(), "sample_rate": ALIGN_SR}
        return (json.dumps(doc, ensure_ascii=False), image, stem_audio, len(doc["words"]))


unload_models_fn = unload_models

NODE_CLASS_MAPPINGS = {"TypesetAlignLyrics": TypesetAlignLyrics}
NODE_DISPLAY_NAME_MAPPINGS = {"TypesetAlignLyrics": "Align Lyrics (forced alignment) (Reprise)"}
