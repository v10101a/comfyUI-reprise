"""Spec for the "Fall For Me" lyric video (look 'dreamy').  python3 scripts/content/ffm_spec.py <tag> -> outputs/ffm/spec_<tag>.json

Timings: hand-merged from prompted per-line faster-whisper chunks + pYIN voiced segments (the app's heuristic
alignment put "Stop thinking" in the instrumental intro, so it is replaced here; see outputs/ffm/NOTES.md).
Note names: pYIN on the full mix, snapped to G minor — approximate, decorative (the footage's own piano roll style).
"""
import json, sys
from pathlib import Path
OUT = Path(__file__).resolve().parents[2] / "outputs/ffm"
END = 37.16
CUT = 36.2   # footage loops back into its dense piano roll + faint title at frame 1086: hand the frame back to it

# (lineId, phrase group, [(text, start, sung_end, note)])
LINES = [
    ("v1", "A", [("stop", 17.22, 17.55, "a3"), ("thinking", 17.56, 18.25, "a3")]),
    ("v2", "A", [("for", 18.34, 18.85, "a3"), ("a", 18.89, 19.15, "bb3"), ("minute", 19.22, 20.84, "bb3")]),
    ("v3", "B", [("the", 21.62, 22.2, "d3"), ("stars", 22.40, 22.6, "d3"), ("are", 22.62, 22.86, "g3"), ("blinking", 22.88, 23.94, "g3")]),
    ("v4", "B", [("they're", 23.98, 24.5, "bb3"), ("waiting", 24.58, 25.45, "bb3")]),
    ("v5", "C", [("come", 25.55, 26.15, "f4"), ("to", 26.2, 26.45, "f4"), ("me", 26.5, 27.1, "d4")]),
    ("v6", "C", [("a", 27.38, 27.62, "d3"), ("little", 27.66, 27.92, "f3"), ("silly", 27.94, 28.5, "d3")]),
    ("v7", "D", [("i'll", 28.55, 29.3, "d3"), ("make", 29.38, 29.58, "g3"), ("you", 29.6, 29.76, "g3"), ("happy", 29.78, 30.2, "g3")]),
    ("v8", "D", [("i'll", 30.27, 30.65, "g3"), ("make", 30.71, 31.0, "bb3"), ("you", 31.06, 31.5, "g3")]),
]
HOOKS = [  # (lineId, [(text, start)], y, size, end)
    ("h1a", [("fall", 31.60)], .245, .165, 34.70),
    ("h1b", [("for", 32.04), ("me", 32.38)], .835, .135, 34.70),
    ("h2a", [("fall", 34.84)], .245, .165, CUT),
    ("h2b", [("for", 35.32), ("me", 36.00)], .835, .135, CUT),
]

def build(tag, v):
    groups = {}
    for lid, g, ws in LINES: groups.setdefault(g, []).append((lid, ws))
    gend = {}
    order = sorted(groups, key=lambda g: groups[g][0][1][0][1])
    starts = [groups[g][0][1][0][1] for g in order]
    for i, g in enumerate(order): gend[g] = starts[i + 1] if i + 1 < len(order) else HOOKS[0][1][0][1]
    words = []
    for g, items in groups.items():
        for row, (lid, ws) in enumerate(items):
            y = v["pos"][g][row]
            for j, (text, s, e, note) in enumerate(ws):
                last = j == len(ws) - 1
                words.append({"id": f"{lid}_{j}", "text": text, "start": s, "end": gend[g] if last else e, "lineId": lid,
                              "placement": v.get("verse_placement", "overlay"), "preset": "pop", "position": {"x": .5, "y": y}, "autoPlace": False,
                              "style": {"fontSize": v["verse_size"], "align": "center"}, **({"note": note} if v.get("notes", True) else {})})
    for lid, ws, y, size, end in HOOKS:
        for j, (text, s) in enumerate(ws):
            words.append({"id": f"{lid}_{j}", "text": text, "start": s, "end": end if j == len(ws) - 1 else s + .4, "lineId": lid,
                          "placement": "behind", "preset": "pop", "position": {"x": .5, "y": v.get("hook_y", {}).get(lid, y)}, "autoPlace": False,
                          "style": {"fontSize": v.get("hook_size", {}).get(lid, size), "align": "center"}})
    words.sort(key=lambda w: w["start"])
    meta = {lid: {"hook": False} for lid, _, _ in LINES} | {lid: {"hook": True} for lid, *_ in HOOKS}
    spec = {"look": {"id": "dreamy", "overrides": v.get("overrides")}, "lineMeta": meta, "words": words,
            "style": {"fontFamily": "Instrument Serif", "fontWeight": 400, "fontSize": v["verse_size"], "fill": "#ffffff", "align": "center"}}
    p = OUT / f"spec_{tag}.json"; p.write_text(json.dumps(spec, indent=1)); print(p)

VARIANTS = {
    "v1": {"verse_size": .062, "pos": {"A": [.80, .90], "B": [.10, .20], "C": [.80, .90], "D": [.10, .20]}},
    "v2": {"verse_size": .072, "overrides": {"verse": {"max": .09, "keepPosition": True}},
           "pos": {"A": [.765, .885], "B": [.095, .215], "C": [.765, .885], "D": [.095, .215]},
           "hook_y": {"h1a": .27, "h1b": .80, "h2a": .27, "h2b": .80}},
    "v3": {"verse_size": .072, "overrides": {"verse": {"max": .09, "keepPosition": True}},
           "pos": {"A": [.74, .875], "B": [.125, .255], "C": [.74, .875], "D": [.125, .255]},
           "hook_y": {"h1a": .315, "h1b": .80, "h2a": .315, "h2b": .80}},
}
if __name__ == "__main__":
    tag = sys.argv[1]; build(tag, VARIANTS[tag])
