"""Validate TypesetAlignLyrics on the demo songs (runs the node's core in-process, CPU, bounded memory).

  ~/ComfyUI/.venv/bin/python scripts/align_validate.py hero|ffm [--fresh]

Writes outputs/align/<song>_words.json (proposed words, NOT applied to any project), <song>_compare.png
(stem waveform + mel spectrogram, old vs new word boxes, onset ticks), <song>_clicks.wav (song + beeps at
new starts), <song>_clicks_old.wav (beeps at the current project starts) and <song>_report.json.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_nodes_dev"))
import types  # noqa: E402
sys.modules.setdefault("folder_paths", types.ModuleType("folder_paths"))  # package __init__ imports Comfy-only nodes
from typeset_nodes import lyric_align as LA  # noqa: E402

OUT = ROOT / "outputs" / "align"
HERO = ROOT / "data/projects/54da2790-92c6-4737-bc43-81a207e47ab5"
FFM = ROOT / "data/projects/14ef9e95-1d22-4bc1-8e42-5a1db01368ee"
FFM_MASTER = Path("/Users/lh1783/Downloads/v10101a/fall for me master 2.wav")
FFM_LYRICS = ("Stop thinking\nFor a minute\nThe stars are blinking\nThey're waiting\nCome to me\nA little silly\n"
              "I'll make you happy\nI'll make you\nFall for me\nFall for me\nFor me\nFor me")
FFM_DUR = 45.733  # M extended the cut to master 172.6 s


CAVEATS = {
    "hero": [
        "Applies to the karaoke sub0-sub5 words (ids given). Hook/surface lines that deliberately start on shot cuts "
        "(s2-wall*, s4-wall*) should keep their cut times; s1-*/s5-*/s6-* hook words can take the new start of the "
        "matching sung word.",
        "Independent check (pYIN voiced entry of the line's first word): old error 580-960 ms, new 10-72 ms.",
        "Every line used to start early (Every 4.24 vs 4.91, Hold 11.54 vs 12.05, Hold 16.38 vs 16.91, Every 18.94 vs 19.94).",
    ],
    "ffm": [
        "No vocal_start needed. The global CTC pass puts 'stop thinking' at 14.68 (intro bleed). The duration-cap "
        "re-anchoring sees 'thinking' would hold 5.7 s with no quiet gap before 'For', and re-aligns the line in a "
        "window ending at 20.79. That gives 18.27/18.71, the same as a hand-set vocal_start of 17.9. The 17.1-18.8 "
        "phrase is an echo that ASRs hear as 'make you fall for me' (W); user: 17.22 is WAY too early.",
        "'For a minute' is sung at 20.79 (stem greedy CTC decodes the m of minute at 21.20), not 18.34.",
        "Hook anchor (user: felt right): first FALL FOR ME within -31/-51/+69 ms. Keep the current hook times. On the "
        "echo the aligner puts 'for' at 35.53 (stem pitch re-attack at 35.54) and 'me' at 36.33 (A#3 at 36.38), "
        "while the current 35.32/36.00 came from Whisper's back-to-back word fill. Optional ear check.",
        "Tags (t1/t2 'for me'): stem and mix agree on one 'for me' at 40.43-40.53/40.63-40.93 and one at "
        "41.83-42.09/42.23-42.49. t2 (41.88) is confirmed. t1 is NOT at 38.18 by the aligner (40.43). There is an "
        "unvoiced energy entry at 38.9 (and Whisper heard 'for me' x4), so a third repeat may start ~38.9. Ear check.",
        "Low confidence is normal on this dense mix (HDemucs leaves bleed). Use the click tracks to verify.",
    ],
}


def load(path: Path, start=0.0, dur=None, sr=44100):
    args = ["ffmpeg", "-v", "error", "-ss", str(start), "-i", str(path)]
    if dur:
        args += ["-t", str(dur)]
    args += ["-ac", "2", "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(args, capture_output=True, check=True).stdout
    return torch.from_numpy(np.frombuffer(raw, np.float32).reshape(-1, 2).T.copy()), sr


def song(name):
    if name == "hero":
        p = json.loads((HERO / "project.json").read_text())
        wave, sr = load(HERO / p["media"]["audio"]["path"])
        old = [w for w in p["words"] if w["lineId"].startswith("sub")]  # karaoke lines = the sung words
        lyrics = p["media"]["lyrics"]
        # independent check: voiced entries of line starts measured with pYIN on the stem (index -> seconds)
        anchors = {6: 4.90, 11: 12.12, 20: 16.96, 25: 19.90}
        return p, wave, sr, lyrics, old, anchors
    p = json.loads((FFM / "project.json").read_text())
    wave, sr = load(FFM_MASTER, 126.857, FFM_DUR)
    old = sorted(p["words"], key=lambda w: w["start"])
    # user: the hook felt right -> those six starts are the validation anchor
    anchors = {i: w["start"] for i, w in enumerate(old) if w["lineId"].startswith("h")}
    return p, wave, sr, FFM_LYRICS, old, anchors


def clicks(wave, sr, times, path, freq=1800.0):
    mix = wave.numpy().T.copy() * 0.7
    n = int(0.035 * sr)
    tt = np.arange(n) / sr
    beep = (np.sin(2 * np.pi * freq * tt) * np.exp(-tt * 60) * 0.5).astype(np.float32)
    for t in times:
        i = int(round(t * sr))
        if 0 <= i < len(mix):
            j = min(len(mix), i + n)
            mix[i:j] += beep[:j - i, None]
    sf.write(path, np.clip(mix, -1, 1), sr, subtype="PCM_16")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("song", choices=["hero", "ffm"])
    ap.add_argument("--fresh", action="store_true", help="recompute the vocal stem")
    ap.add_argument("--separator", default="hdemucs")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(6)
    proj, wave, sr, lyrics, old, anchors = song(a.song)
    stem_path = OUT / f"{a.song}_vocals.wav"
    t0 = time.monotonic()
    vocals = None
    if stem_path.exists() and not a.fresh and a.separator == "hdemucs":
        v, vsr = sf.read(stem_path, dtype="float32")
        vocals = torch.from_numpy(v)
    # No hand-set vocal_start by default (ALIGN_VOCAL_START=17.9 reproduces the earlier hand-windowed run).
    vs = float(__import__("os").environ.get("ALIGN_VOCAL_START", 0)) if a.song == "ffm" else 0.0
    doc, stem16, extra = LA.align_lyrics(wave, sr, lyrics, vocals=vocals, vocal_start=vs, vocals_sr=16000 if vocals is not None else None,
                                         separator=a.separator, progress=lambda m: print(f"  {time.monotonic() - t0:6.1f}s {m}", flush=True))
    if vocals is None and a.separator == "hdemucs":
        sf.write(stem_path, stem16.numpy(), 16000, subtype="FLOAT")
    LA.unload_models()
    print(f"aligned in {time.monotonic() - t0:.1f}s")
    new = doc["words"]
    import librosa
    y = stem16.numpy()
    env = librosa.onset.onset_strength(y=y, sr=16000, hop_length=160, n_fft=1024, lag=2, max_size=3)
    ons = librosa.onset.onset_detect(onset_envelope=env, sr=16000, hop_length=160, units="time", delta=0.04, wait=5)
    snap_onsets = extra["onsets"]

    # pair old project words with aligned words in order (same lyric tokens)
    n = min(len(old), len(new))
    rows, d_old, d_new, d_ctc = [], [], [], []
    for i in range(n):
        o, w = old[i], new[i]
        assert LA.normalize_word(o["text"]) == LA.normalize_word(w["text"]), (i, o["text"], w["text"])
        do, dn, dc = LA.nearest(ons, o["start"]), LA.nearest(ons, w["start"]), LA.nearest(ons, w["ctcStart"] or w["start"])
        d_old.append(do); d_new.append(dn); d_ctc.append(dc)
        rows.append({"i": i, "text": w["text"], "lineId": o["lineId"], "oldStart": o["start"], "newStart": w["start"],
                     "ctcStart": w.get("ctcStart"), "delta": round(w["start"] - o["start"], 3), "newEnd": w["end"],
                     "oldToOnset": round(do, 3), "ctcToOnset": round(dc, 3), "newToOnset": round(dn, 3),
                     "confidence": w["confidence"], "low": w["lowConfidence"], "id": o.get("id")})

    def st(x):
        x = np.abs(np.array(x))
        return {"median_ms": round(float(np.median(x)) * 1000, 1), "mean_ms": round(float(x.mean()) * 1000, 1),
                "p90_ms": round(float(np.percentile(x, 90)) * 1000, 1), "max_ms": round(float(x.max()) * 1000, 1),
                "within_50ms": int((x <= .05).sum()), "within_100ms": int((x <= .1).sum()), "n": int(len(x))}
    # chance baseline: random times inside the sung span
    rng = np.random.default_rng(0)
    lo, hi = new[0]["start"], new[n - 1]["end"]
    rnd = [LA.nearest(ons, t) for t in rng.uniform(lo, hi, 2000)]
    report = {"song": a.song, "onsets": len(ons), "onset_detector": "librosa broadband spectral flux on the stem (dense; for the distance stats)", "old_to_onset": st(d_old), "ctc_to_onset": st(d_ctc),
              "new_to_onset": st(d_new), "random_to_onset": st(rnd), "stats": doc["stats"], "words": rows}
    if anchors:
        report["anchor_kind"] = {"hero": "pYIN voiced entry of the line's first word on the stem",
                                 "ffm": "current hook starts (user: 'felt right')"}[a.song]
        report["anchor_check"] = [{"text": new[i]["text"], "anchor": t, "old": old[i]["start"], "ctc": new[i]["ctcStart"], "new": new[i]["start"],
                                   "old_ms": round((old[i]["start"] - t) * 1000), "ctc_ms": round((new[i]["ctcStart"] - t) * 1000),
                                   "new_ms": round((new[i]["start"] - t) * 1000)} for i, t in anchors.items() if i < len(new)]
        for k in ("old_ms", "ctc_ms", "new_ms"):
            report["anchor_check_mean_abs_" + k] = round(float(np.mean([abs(x[k]) for x in report["anchor_check"]])), 1)
    (OUT / f"{a.song}_report.json").write_text(json.dumps(report, indent=1))

    proposed = {"source": doc["source"], "model": doc["model"], "song": a.song, "projectId": proj["id"],
                "note": "Proposed timings from TypesetAlignLyrics; NOT applied. 'id' is the matching project word "
                        "(karaoke subN words in the hero). Ends are acoustic (sustained-note) ends; keep authored "
                        "line-hold ends if the design wants them.",
                "words": [{**w, **({"id": old[i].get("id"), "projectLineId": old[i]["lineId"], "oldStart": old[i]["start"]} if i < n else {})}
                          for i, w in enumerate(new)], "lines": doc["lines"]}
    proposed["caveats"] = CAVEATS[a.song]
    (OUT / f"{a.song}_words.json").write_text(json.dumps(proposed, indent=1))

    dur = min(len(stem16) / 16000, proj["duration"] + 0.5)
    first = max(0.0, min(w["start"] for w in new[:n]) - 1.0)
    img = LA.render_preview(stem16, [("old", [dict(o, lowConfidence=False) for o in old[:n]], (120, 170, 255)),
                                     ("new", new[:n], (255, 110, 190))], onsets=snap_onsets, t0=first, t1=dur, px_per_s=110,
                            title=f"{a.song}: vocal stem (HDemucs) · mel · green = stem onsets · blue = current project starts · pink = TypesetAlignLyrics")
    img.save(OUT / f"{a.song}_compare.png")
    clicks(wave, sr, [w["start"] for w in new[:n]], OUT / f"{a.song}_clicks.wav")
    clicks(wave, sr, [o["start"] for o in old[:n]], OUT / f"{a.song}_clicks_old.wav", freq=1200.0)

    print(json.dumps({k: report[k] for k in ("old_to_onset", "ctc_to_onset", "new_to_onset", "random_to_onset")}, indent=0))
    if anchors:
        print("anchors:", [(x["text"], x["anchor"], x["old_ms"], x["ctc_ms"], x["new_ms"]) for x in report["anchor_check"]],
              {k: v for k, v in report.items() if k.startswith("anchor_check_mean")})
    for r in rows:
        print(f"{r['i']:3d} {r['text']:<10} {r['lineId']:<6} old {r['oldStart']:7.3f}  ctc {r['ctcStart'] or 0:7.3f}  new {r['newStart']:7.3f}"
              f"  Δ {r['delta']:+.3f}  onset old {r['oldToOnset']*1000:+5.0f} new {r['newToOnset']*1000:+5.0f}ms  conf {r['confidence']:.2f}{' LOW' if r['low'] else ''}")


if __name__ == "__main__":
    main()
