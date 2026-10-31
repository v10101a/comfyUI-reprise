"""Retime the hero to the forced-alignment word starts (outputs/align/hero_words.json).

  server/.venv/bin/python scripts/content/hero_retime.py <project-id> [--dry]

- sub0–5 karaoke words: aligned start; end = next word's start within the line (contiguous karaoke);
  the line's last word keeps max(aligned end, old end) so the line holds as before.
- Title/hook words that stand for a sung word move to that word's aligned start (s1 WALK…RAIN, s6 EVERY/WORD/I/KNOW),
  tunnel surfaces s5 (HOLD/ON/LET IT/SHOW) likewise; designed hold ends are kept (RAIN → cut, s6 → end,
  s5 pairs → next pair / just before the S6 cut).
- s2 wall rows: EVERY stays on the cut (4.33); SIGN/REPEATS/YOUR/NAME reveal on their sung starts.
- s4 plaza: HOLD stays on the drop (11.50); ON reveals on sung "on" (12.81).
- pinTiming on s2-wall*, s4-wall*, s3-count*, s3-meta, s3-hud* (cut/beat/display times). timing.leadMs = 40.
Matches words by id, so it works on reframed copies (same ids).
"""
import json, sys
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[2]; API = "http://127.0.0.1:8787"
A = {w["id"]: w for w in json.loads((ROOT / "outputs/align/hero_words.json").read_text())["words"] if w.get("id")}
S = lambda wid: round(A[wid]["start"], 3)

TITLE = {  # title word id prefix -> (aligned sub id for start, end rule)
    "s1-WALK": ("sub0-00", "next:s1-THROUGH"), "s1-THROUGH": ("sub0-02", "next:s1-NEON"),
    "s1-NEON": ("sub0-04", "next:s1-RAIN"), "s1-RAIN": ("sub0-05", "keep"),
    "s6-EVERY": ("sub5-25", "keep"), "s6-WORD": ("sub5-26", "keep"), "s6-I": ("sub5-27", "keep"), "s6-KNOW": ("sub5-28", "keep"),
    "s5-L1": ("sub4-20", "next:s5-L2"), "s5-R1": ("sub4-21", "next:s5-L2"),
    "s5-L2": ("sub4-22", "abs:18.93"), "s5-R2": ("sub4-24", "abs:18.93"),
}
WALL_WORD = {"SIGN": "sub1-07", "REPEATS": "sub1-08", "YOUR": "sub1-09", "NAME": "sub1-10"}
PIN = ("s2-wall", "s4-wall", "s3-count", "s3-meta", "s3-hud")

def retime(p):
    W = p["words"]; log = []
    # karaoke
    by_line = {}
    for w in W:
        if w["id"] in A and w["lineId"].startswith("sub"): by_line.setdefault(w["lineId"], []).append(w)
    for ln, ws in by_line.items():
        ws.sort(key=lambda w: S(w["id"]))
        for i, w in enumerate(ws):
            old = (w["start"], w["end"]); w["start"] = S(w["id"])
            w["end"] = S(ws[i + 1]["id"]) if i + 1 < len(ws) else round(max(A[w["id"]]["end"], old[1]), 3)
            log.append((w["id"], w["text"], old, (w["start"], w["end"])))
    # titles / tunnel
    first = {}
    for w in W: first.setdefault(w["lineId"], w)
    for w in W:
        r = TITLE.get(w["lineId"])
        if not r: continue
        old = (w["start"], w["end"]); w["start"] = S(r[0])
        if r[1].startswith("abs:"): w["end"] = float(r[1][4:])
        log.append((w["id"], w["text"], old, (w["start"], w["end"])))
    for w in W:
        r = TITLE.get(w["lineId"])
        if r and r[1].startswith("next:"):
            w["end"] = first[r[1][5:]]["start"]
    # wall rows / plaza
    for w in W:
        if w["lineId"].startswith("s2-wall") and w["text"] in WALL_WORD:
            old = (w["start"], w["end"]); w["start"] = S(WALL_WORD[w["text"]]); log.append((w["id"], w["text"], old, (w["start"], w["end"])))
        if w["lineId"] == "s4-wallR":
            old = (w["start"], w["end"]); w["start"] = S("sub2-12"); log.append((w["id"], w["text"], old, (w["start"], w["end"])))
    lm = dict(p.get("lineMeta") or {})
    for lid in {w["lineId"] for w in W if w["lineId"].startswith(PIN)}:
        lm[lid] = {**(lm.get(lid) or {}), "pinTiming": True}
    p["lineMeta"] = lm; p["timing"] = {**(p.get("timing") or {}), "leadMs": 40}
    return log

if __name__ == "__main__":
    pid = sys.argv[1]; c = httpx.Client(timeout=60)
    p = c.get(f"{API}/api/projects/{pid}").json()
    log = retime(p)
    for wid, t, o, n in log: print(f"{wid:16} {t:10} {o[0]:6.2f}-{o[1]:6.2f} -> {n[0]:6.3f}-{n[1]:6.3f}")
    bad = [w["id"] for w in p["words"] if w["end"] <= w["start"]]
    if bad: raise SystemExit(f"non-positive durations: {bad}")
    if "--dry" not in sys.argv:
        c.put(f"{API}/api/projects/{pid}", json=p).raise_for_status(); print("applied", pid, p["timing"])
