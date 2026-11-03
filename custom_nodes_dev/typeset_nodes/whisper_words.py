"""WhisperWords — word-level timestamps from a ComfyUI AUDIO via faster-whisper (CPU, int8).

Output is the SCHEMA §2 `words.json` document as a STRING:

    {"source": "faster-whisper" | "aligned", "model": "small", "language": "en",
     "words": [{"text": "neon", "start": 1.02, "end": 1.31, "confidence": 0.93, "lineId": "l0"}],
     "lines": [{"id": "l0", "text": "neon lights", "start": 1.02, "end": 1.80}]}

Without lyrics, lines are Whisper segments. With lyrics (newline-separated), the recognized words are
aligned to the lyric tokens with difflib.SequenceMatcher on normalized tokens; the output then uses the
lyric spelling/casing and lyric lines, keeping Whisper's timings and interpolating timings for lyric
words Whisper missed. Models are cached per process (first use downloads ~75–1500 MB from HF).
"""
import difflib
import json
import re
import threading

import numpy as np
import torch

_MODELS = {}
_LOCK = threading.Lock()
TARGET_SR = 16000
MIN_WORD = 0.05       # seconds; enforce end > start
MAX_LEAD = 1.0        # seconds; a line-initial word longer than this starts at end - MAX_LEAD
GAP_FILL = 0.30       # seconds per interpolated word at the edges


def _get_model(size: str):
    from faster_whisper import WhisperModel
    with _LOCK:
        if size not in _MODELS:
            _MODELS[size] = WhisperModel(size, device="cpu", compute_type="int8")
        return _MODELS[size]


def _to_mono_16k(audio) -> np.ndarray:
    wav = audio["waveform"]
    if wav.ndim == 3:
        wav = wav[0]
    sr = int(audio["sample_rate"])
    mono = wav.float().mean(dim=0)
    if sr != TARGET_SR:
        try:
            import torchaudio.functional as AF
            mono = AF.resample(mono, sr, TARGET_SR)
        except Exception:
            import librosa
            mono = torch.from_numpy(librosa.resample(mono.cpu().numpy(), orig_sr=sr, target_sr=TARGET_SR))
    return mono.cpu().numpy().astype(np.float32)


def _norm(tok: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", tok.lower())


def transcribe_words(audio, model_size="small", language="auto", initial_prompt=None):
    """Run faster-whisper; return (rec_words, segments, detected_language).
    rec_words: list of dicts {text, start, end, confidence, seg}  (seg = segment index)."""
    model = _get_model(model_size)
    samples = _to_mono_16k(audio)
    lang = None if (not language or language.strip().lower() in ("auto", "")) else language.strip()
    kwargs = dict(word_timestamps=True, language=lang, beam_size=5, condition_on_previous_text=False,
                  vad_filter=False)
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt
    seg_iter, info = model.transcribe(samples, **kwargs)
    rec, segments = [], []
    for si, seg in enumerate(seg_iter):
        segments.append({"id": f"l{si}", "text": seg.text.strip(), "start": float(seg.start), "end": float(seg.end)})
        for w in (seg.words or []):
            text = w.word.strip()
            if not text:
                continue
            rec.append({"text": text, "start": float(w.start), "end": float(w.end),
                        "confidence": float(getattr(w, "probability", 1.0)), "seg": si})
    return rec, segments, (info.language if info else None)


def _trim_line_starts(words):
    """Whisper glues the first word of a line to the end of the previous one across an instrumental
    pause (e.g. "Every" 2.2–5.2 s). Sung line starts are short, so keep the end and trim the start."""
    prev_line = None
    for w in words:
        if w["lineId"] != prev_line and w["end"] - w["start"] > MAX_LEAD:
            w["start"] = w["end"] - MAX_LEAD
        prev_line = w["lineId"]
    return words


def _fix_monotonic(words):
    prev_end = 0.0
    for w in words:
        if w["start"] < prev_end:
            w["start"] = prev_end
        if w["end"] <= w["start"] + MIN_WORD:
            w["end"] = w["start"] + MIN_WORD
        prev_end = w["end"]
    return words


_SECTION = re.compile(r"^\s*[\[(][^\])]*[\])]\s*$")  # [verse], [chorus], (x2) — song-structure tags, not sung


def lyric_lines_of(lyrics: str) -> list[str]:
    return [ln.strip() for ln in lyrics.replace("\r", "").split("\n") if ln.strip() and not _SECTION.match(ln)]


def align_to_lyrics(rec, lyrics: str):
    """Snap recognized words to lyric tokens. Returns (words, lines)."""
    lyric_lines = lyric_lines_of(lyrics)
    toks = []  # (line_idx, token)
    for li, ln in enumerate(lyric_lines):
        for t in ln.split():
            toks.append((li, t))
    if not toks:
        return [], []
    a = [_norm(r["text"]) for r in rec]
    b = [_norm(t) for _, t in toks]
    timing = [None] * len(toks)     # (start, end, conf)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                r = rec[i1 + k]
                timing[j1 + k] = (r["start"], r["end"], r["confidence"])
        elif tag == "replace":
            n_rec, n_lyr = i2 - i1, j2 - j1
            if n_rec == n_lyr:
                for k in range(n_lyr):
                    r = rec[i1 + k]
                    timing[j1 + k] = (r["start"], r["end"], r["confidence"] * 0.5)
            else:
                # spread the lyric tokens over the recognized span (misrecognitions / merged words)
                span_s, span_e = rec[i1]["start"], rec[i2 - 1]["end"]
                step = (span_e - span_s) / n_lyr if n_lyr else 0
                for k in range(n_lyr):
                    timing[j1 + k] = (span_s + k * step, span_s + (k + 1) * step, 0.3)
        # 'insert' (lyric words Whisper missed) -> interpolated below; 'delete' (extra words) -> dropped

    # interpolate missing timings
    n = len(toks)
    known = [i for i in range(n) if timing[i] is not None]
    if not known:
        return [], []
    i = 0
    while i < n:
        if timing[i] is not None:
            i += 1
            continue
        j = i
        while j < n and timing[j] is None:
            j += 1
        gap = j - i
        prev_end = timing[i - 1][1] if i > 0 else None
        next_start = timing[j][0] if j < n else None
        if prev_end is None:
            lo, hi = max(0.0, next_start - GAP_FILL * gap), next_start
        elif next_start is None:
            lo, hi = prev_end, prev_end + GAP_FILL * gap
        else:
            lo, hi = prev_end, max(next_start, prev_end + MIN_WORD * gap)
            if hi - lo > GAP_FILL * gap * 2:
                # A long pause around missed words: a missed line start is sung just before the next
                # recognized word (after the pause); a missed line end just after the previous one.
                if toks[i][0] != toks[i - 1][0]:
                    lo = hi - GAP_FILL * gap
                else:
                    hi = lo + GAP_FILL * gap
        step = (hi - lo) / gap
        for k in range(gap):
            timing[i + k] = (lo + k * step, lo + (k + 1) * step, 0.0)
        i = j

    words = []
    for (li, tok), (s, e, c) in zip(toks, timing):
        words.append({"text": tok, "start": round(s, 3), "end": round(e, 3),
                      "confidence": round(c, 3), "lineId": f"l{li}"})
    _trim_line_starts(words)
    _fix_monotonic(words)
    for w in words:
        w["start"], w["end"] = round(w["start"], 3), round(w["end"], 3)
    lines = []
    for li, ln in enumerate(lyric_lines):
        ws = [w for w in words if w["lineId"] == f"l{li}"]
        if ws:
            lines.append({"id": f"l{li}", "text": ln, "start": ws[0]["start"], "end": ws[-1]["end"]})
    return words, lines


def build_words_json(rec, segments, language, model_size, lyrics=""):
    if lyrics and lyrics.strip():
        words, lines = align_to_lyrics(rec, lyrics)
        source = "aligned"
        if not words:  # nothing matched at all -> fall back to raw recognition
            words, lines, source = None, None, "faster-whisper"
    else:
        words, lines, source = None, None, "faster-whisper"
    if words is None:
        words = [{"text": r["text"], "start": round(r["start"], 3), "end": round(r["end"], 3),
                  "confidence": round(r["confidence"], 3), "lineId": f"l{r['seg']}"} for r in rec]
        _trim_line_starts(words)
        _fix_monotonic(words)
        for w in words:
            w["start"], w["end"] = round(w["start"], 3), round(w["end"], 3)
        used = {w["lineId"] for w in words}
        lines = [{"id": s["id"], "text": s["text"], "start": round(s["start"], 3), "end": round(s["end"], 3)}
                 for s in segments if s["id"] in used]
    words.sort(key=lambda w: w["start"])
    return {"source": source, "model": model_size, "language": language or "unknown",
            "words": words, "lines": lines}


class WhisperWords:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model_size": (["tiny", "base", "small", "medium"], {"default": "small"}),
                "language": ("STRING", {"default": "auto", "tooltip": "ISO code (en, es, ...) or 'auto'."}),
                "lyrics": ("STRING", {"default": "", "multiline": True,
                                      "tooltip": "Optional lyrics, one line per lyric line. Words are snapped to these."}),
            },
            "optional": {
                "lyrics_as_prompt": ("BOOLEAN", {"default": True,
                                                 "tooltip": "Feed the lyrics to Whisper as initial_prompt to bias vocabulary."}),
            },
        }

    RETURN_TYPES = ("STRING", "INT", "STRING")
    RETURN_NAMES = ("words_json", "word_count", "language")
    FUNCTION = "run"
    CATEGORY = "Reprise/audio"

    def run(self, audio, model_size="small", language="auto", lyrics="", lyrics_as_prompt=True):
        prompt = None
        if lyrics_as_prompt and lyrics and lyrics.strip():
            prompt = " ".join(" ".join(lyric_lines_of(lyrics)).split())[:600]
        rec, segments, detected = transcribe_words(audio, model_size, language, prompt)
        doc = build_words_json(rec, segments, detected, model_size, lyrics)
        return (json.dumps(doc, ensure_ascii=False), len(doc["words"]), doc["language"])


NODE_CLASS_MAPPINGS = {"WhisperWords": WhisperWords}
NODE_DISPLAY_NAME_MAPPINGS = {"WhisperWords": "Whisper → Words JSON (Reprise)"}
