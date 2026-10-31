"""Spec for the "Fall For Me" lyric video (look 'dreamy').

  python3 scripts/content/ffm_spec.py <tag> [--times outputs/align/ffm_words.json]   (or --times=...)   -> outputs/ffm/spec_<tag>.json

Word timing is a separate layer: scripts/content/ffm_words.json holds every word (id, text, start, end, note, role).
`--times=<file>` (e.g. outputs/align/ffm_words.json, A's forced alignment) swaps in aligned start/end for the verse and tag words, matched
to the lyric word list in order by normalized text. Hook words ("FALL / FOR ME" at 31.6 s and 34.84 s) keep their times
(user: keep the hook). Times are video seconds = master seconds - 126.857. Unmatched words keep the table times; the
match report is printed and written next to the spec.
Note names: pYIN on the full mix, snapped to G minor. They are approximate and decorative (the footage's own piano-roll style).
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; OUT = ROOT / "outputs/ffm"
TABLE = Path(__file__).with_name("ffm_words.json")
ALIGN = ROOT / "outputs/align/ffm_words.json"
OFFSET = 126.857

def norm(s): return re.sub(r"[^a-z0-9']", "", s.lower().replace("’", "'"))

def load_times(path):
    """Aligned words: [{text,start,end,id?}] or {"words":[...]}. Video seconds, or master seconds when the file says
    "timebase": "master" (or any start > 60). `id` (= a table word id, as A's TypesetAlignLyrics output has) wins over text order."""
    d = json.loads(Path(path).read_text()); ws = d["words"] if isinstance(d, dict) else d
    master = isinstance(d, dict) and d.get("timebase") == "master" or any(w["start"] > 60 for w in ws)
    sh = OFFSET if master else 0
    return [{"id": w.get("id"), "text": w.get("text") or w.get("word"), "start": w["start"] - sh, "end": w["end"] - sh} for w in ws]

def apply_times(words, aligned):
    """By id when the aligned file has ids; else sequential by normalized text (lookahead 4). Hook words are consumed
    but keep their authored times (user-approved)."""
    report = []; ids = {a["id"]: a for a in aligned if a.get("id")}; j = 0
    for w in words:
        a = ids.get(w["id"])
        if a is None and not ids:
            for k in range(j, min(j + 5, len(aligned))):
                if norm(aligned[k]["text"]) == norm(w["text"]): a = aligned[k]; j = k + 1; break
        if w["role"] == "hook": continue
        if a is None: report.append(f"unmatched {w['id']} '{w['text']}' kept {w['start']:.2f}"); continue
        report.append(f"{w['id']:6} {w['text']:9} {w['start']:6.2f} -> {a['start']:6.2f}")
        w["start"], w["end"] = round(a["start"], 3), round(a["end"], 3)
    return report

def build(tag, v, times=None):
    table = json.loads(TABLE.read_text()); words = table["words"]; layout = table["layout"]
    report = apply_times(words, load_times(times)) if times else []
    by_line = {}
    for w in words: by_line.setdefault(w["lineId"], []).append(w)
    lines = sorted(by_line.items(), key=lambda kv: min(w["start"] for w in kv[1]))
    # A phrase group (two verse lines) stays up until the next group starts; hook/tag lines until their "until".
    groups = {}
    for lid, ws in lines:
        g = layout[lid].get("group")
        if g: groups.setdefault(g, []).append(lid)
    gstart = {g: min(w["start"] for lid in lids for w in by_line[lid]) for g, lids in groups.items()}
    nexts = sorted(set(gstart.values()) | {min(w["start"] for w in by_line[l]) for l, _ in lines if not layout[l].get("group")})
    out = []
    for lid, ws in lines:
        L = layout[lid]; ws = sorted(ws, key=lambda w: w["start"])
        if L.get("group"):
            s0 = gstart[L["group"]]; end = next((t for t in nexts if t > s0 + 1e-6), table["duration"] + .5)
        else: end = L["until"] if isinstance(L["until"], (int, float)) else min(w["start"] for w in by_line[L["until"]]) if L["until"] in by_line else table["duration"] + .5
        hook = words and ws[0]["role"] in ("hook", "tag")
        size = v["verse_size"] if not hook else L["size"]
        y = v.get("pos", {}).get(lid, L["y"])
        for j, w in enumerate(ws):
            last = j == len(ws) - 1
            e = end if last else (w["end"] if not hook else max(w["end"], w["start"] + .4))
            out.append({"id": w["id"], "text": w["text"], "start": w["start"], "end": round(max(e, w["start"] + .05), 3), "lineId": lid,
                        "placement": "behind" if hook else "overlay", "preset": "pop", "position": {"x": .5, "y": y}, "autoPlace": False,
                        "style": {"fontSize": size, "align": "center"}, **({"note": w["note"]} if w.get("note") and not hook else {})})
    out.sort(key=lambda w: w["start"])
    meta = {lid: {"hook": ws[0]["role"] in ("hook", "tag")} for lid, ws in by_line.items()}
    spec = {"look": {"id": "dreamy", "overrides": v.get("overrides")}, "lineMeta": meta, "words": out, **({"timing": v["timing"]} if v.get("timing") else {}),
            "style": {"fontFamily": "Instrument Serif", "fontWeight": 400, "fontSize": v["verse_size"], "fill": "#ffffff", "align": "center"}}
    p = OUT / f"spec_{tag}.json"; p.write_text(json.dumps(spec, indent=1)); print(p)
    if report: (OUT / f"spec_{tag}_timing.txt").write_text("\n".join(report) + "\n"); print("\n".join(report))

VARIANTS = {
    "v3": {"verse_size": .072, "overrides": {"verse": {"max": .09, "keepPosition": True}}},
}
VARIANTS["v4"] = VARIANTS["v3"]
# v5: A's acoustic alignment (--times) + perceived-sync lead; vocalStart keeps future words jobs out of the intro.
VARIANTS["v5"] = {**VARIANTS["v3"], "timing": {"leadMs": 40, "vocalStart": 17.9}}
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build outputs/ffm/spec_<tag>.json")
    ap.add_argument("tag"); ap.add_argument("--times", help="aligned words JSON (e.g. outputs/align/ffm_words.json); '--times X' or '--times=X'")
    a = ap.parse_args()   # unknown args are an error
    if a.times and not Path(a.times).exists(): ap.error(f"--times file not found: {a.times}")
    build(a.tag, VARIANTS.get(a.tag, VARIANTS["v4"]), a.times)
