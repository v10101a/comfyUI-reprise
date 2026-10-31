"""Typography spec for the hero (writes outputs/hero/spec_<ver>.json). Times = aligned words from the words job.
Design system: BIG = one display word at a time (Anton, bone white), the moment; SMALL = a constant mono lyric
'subtitle track' bottom-left (Space Mono, karaoke), the reading line. Surfaces carry the lines that belong to a wall.
"""
import json, sys
from pathlib import Path
V = sys.argv[1] if len(sys.argv) > 1 else "v1"
BONE, LIME, PINK = "#F3EEE4", "#D8FF62", "#FF4FA3"
words = []
def W(text, s, e, line, placement="behind", preset="pop", **kw):
    words.append({"id": f"{line}-{len(words):02d}", "text": text, "start": round(s, 3), "end": round(e, 3), "lineId": line,
                  "placement": placement, "preset": preset, **kw})
def big(size, **st): return {"fontFamily": "Anton", "fontWeight": 400, "fontSize": size, "fill": BONE, "letterSpacing": -0.01, "align": "center", **st}
def mono(size=0.032, **st): return {"fontFamily": "Space Mono", "fontWeight": 400, "fontSize": size, "fill": BONE, "letterSpacing": 0.04, "align": "left", **st}

# --- subtitle track (constant, small, lower-left) ---
SUB = {"x": 0.055, "y": 0.915}
for i, line in enumerate([
    [("walk", 0.0, .26), ("me", .26, .52), ("through", .52, .88), ("the", .88, 1.16), ("neon", 1.16, 1.56), ("rain", 1.56, 4.2)],
    [("every", 4.24, 5.24), ("sign", 5.24, 5.64), ("repeats", 5.64, 6.10), ("your", 6.10, 6.58), ("name", 6.58, 7.3)],
    [("hold", 11.54, 12.38), ("on,", 12.38, 13.06), ("say", 13.14, 13.50), ("it", 13.50, 13.68), ("slow", 13.68, 14.1)],
    [("louder", 14.18, 14.92), ("than", 14.92, 15.28), ("the", 15.28, 15.58), ("radio", 15.58, 16.3)],
    [("hold", 16.38, 17.20), ("on,", 17.20, 17.92), ("let", 17.94, 18.40), ("it", 18.40, 18.54), ("show", 18.54, 18.93)],
    [("every", 18.94, 20.30), ("word", 20.30, 20.72), ("i", 20.72, 21.02), ("know", 21.02, 22.2)]]):
    for t, s, e in line: W(t, s, e, f"sub{i}", "overlay", "karaoke", position=SUB, autoPlace=False, style=mono())

# --- S1 0–4.33: one huge word at a time behind her head ---
for t, s, e in [("WALK", 0.0, .52), ("THROUGH", .52, 1.16), ("NEON", 1.16, 1.56), ("RAIN", 1.56, 4.30)]:
    W(t, s, e, f"s1-{t}", "behind", "pop", position={"x": .5, "y": .30}, autoPlace=False, style=big(0.40, shadow=0.35))

# --- S2 4.33–7.33: the wall says it (surface, paint) ---
INK = "#121212"
for t, s, sid in [("EVERY", 4.33, "wall1"), ("SIGN", 5.24, "wall1"), ("REPEATS", 5.64, "wall2"), ("YOUR", 6.10, "wall3"), ("NAME", 6.58, "wall3")]:
    W(t, s, 7.32, f"s2-{sid}", "surface", "pop", surfaceId=sid, style=big(0.30, fontFamily="Bebas Neue", fill=INK, letterSpacing=0.02))

# --- S3 7.33–11.50: instrumental, HUD on her head ---
W("your name", 7.34, 9.12, "s3-hud1", "anchor", "hud", anchor={"trackId": "person0", "dx": 0.20, "dy": -0.16}, style=mono(0.05, fill=LIME))
W("hold on", 9.13, 11.49, "s3-hud2", "anchor", "hud", anchor={"trackId": "person0", "dx": -0.30, "dy": 0.10}, style=mono(0.05, fill=LIME))

# count-in to the drop, on the beat grid (bars of 2.4 s from 1.93 s)
for n, (s0, s1) in zip("4321", [(9.13, 9.73), (9.73, 10.31), (10.31, 10.94), (10.94, 11.49)]):
    W(n, s0, s1, f"s3-count{n}", "overlay", "none", position={"x": .9, "y": .80}, autoPlace=False, style=mono(0.12, fill=LIME, fontWeight=700, align="center"))
W("NEON RAIN  ·  100 BPM  ·  TAKE 03", 7.34, 11.49, "s3-meta", "overlay", "none", position={"x": .055, "y": .085}, autoPlace=False, style=mono(0.024, fill=LIME))

# --- S4 11.50–13.92: DROP. HOLD ON painted across the plaza wall, she stands in the gap ---
W("HOLD", 11.50, 13.92, "s4-wallL", "surface", "pop", surfaceId="plazaL", style=big(0.5))
W("ON", 12.38, 13.92, "s4-wallR", "surface", "pop", surfaceId="plazaR", style=big(0.5))

# --- G1 13.92–16.33: generated LOUDER (in the plate). Only the subtitle. ---

# --- S5 16.33–18.75: tunnel walls light up (neon surfaces) ---
W("HOLD", 16.38, 17.94, "s5-L1", "surface", "pop", surfaceId="tunnelL", style=big(0.3, fill=PINK))
W("ON", 17.20, 17.94, "s5-R1", "surface", "pop", surfaceId="tunnelR", style=big(0.3, fill=PINK))
W("LET IT", 17.94, 18.74, "s5-L2", "surface", "pop", surfaceId="tunnelL", style=big(0.3, fill=PINK))
W("SHOW", 18.40, 18.74, "s5-R2", "surface", "pop", surfaceId="tunnelR", style=big(0.3, fill=PINK))

# --- S4b 18.75–22.42: every word I know, 2x2 around her, behind ---
for t, s, pos in [("EVERY", 18.94, (.30, .30)), ("WORD", 20.30, (.70, .30)), ("I", 20.72, (.39, .62)), ("KNOW", 21.02, (.70, .62))]:
    W(t, s, 22.42, f"s6-{t}", "behind", "pop", position={"x": pos[0], "y": pos[1]}, autoPlace=False, style=big(0.30, shadow=0.35))

surfaces = [
    {"id": "wall1", "label": "S2 wall row 1", "keyFrame": 120, "material": "paint", "corners": [[.36, .14], [.96, .14], [.96, .36], [.36, .36]]},
    {"id": "wall2", "label": "S2 wall row 2", "keyFrame": 120, "material": "paint", "corners": [[.36, .36], [.96, .36], [.96, .58], [.36, .58]]},
    {"id": "wall3", "label": "S2 wall row 3", "keyFrame": 120, "material": "paint", "corners": [[.36, .58], [.96, .58], [.96, .80], [.36, .80]]},
    {"id": "plazaL", "label": "S4 plaza wall, left of her (static)", "keyFrame": 290, "material": "flat", "noTrack": True, "corners": [[.03, .14], [.525, .14], [.525, .64], [.03, .64]]},
    {"id": "plazaR", "label": "S4 plaza wall, right of her (static)", "keyFrame": 290, "material": "flat", "noTrack": True, "corners": [[.475, .14], [.97, .14], [.97, .64], [.475, .64]]},
    {"id": "tunnelL", "label": "S5 left tunnel wall", "keyFrame": 400, "material": "neon", "corners": [[.0, .05], [.42, .33], [.42, .52], [.0, .93]]},
    {"id": "tunnelR", "label": "S5 right tunnel wall", "keyFrame": 400, "material": "neon", "corners": [[.62, .33], [1.0, .08], [1.0, .93], [.62, .53]]},
]
spec = {"version": V, "surfaces": surfaces, "words": words}
Path(f"outputs/hero/spec_{V}.json").write_text(json.dumps(spec, indent=1)); print(len(words), "words ->", f"outputs/hero/spec_{V}.json")
