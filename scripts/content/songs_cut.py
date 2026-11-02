"""Rebuild the so I die / Playboi review cuts, optionally with lip-synced takes swapped in.

The EDLs are the ones Poppy used for so I die v5 (variants E, F) and Playboi v6; a `--tag` swaps every
clips/lipsync take for `<take>/<tag>/<take>_<tag>_mux.mp4` (made by scripts/lipsync_pass.py) when that file exists.

  python3 scripts/content/songs_cut.py so-i-die E F --tag latentsync
  python3 scripts/content/songs_cut.py playboi v6 --tag latentsync

Outputs: outputs/songs/so-i-die/edit_v5/<variant>[_<tag>]/so_i_die_v5<variant>[_<tag>]_review.mp4 and
outputs/songs/playboi/edit_v6[_<tag>]/playboi_v6[_<tag>]_review.mp4 (plus edl.json, parts, silent cut).
"""
import argparse
import json
import subprocess
from pathlib import Path

R = Path(__file__).resolve().parents[2]
FPS = 24

# The angel final's film grade (outputs/ffm_angel/v3/film_grade.txt): halation + bloom + soft + grain on the whole cut.
FILM = ("format=gbrp,split=4[a][b][c][d];[b]curves=all='0/0 0.6/0 1/1',gblur=sigma=40,colorchannelmixer=rr=1:gg=0.62:bb=0.45[hal];"
        "[c]curves=all='0/0 0.5/0 1/1',gblur=sigma=12[bloom];[d]gblur=sigma=2.2[soft];[a][soft]blend=all_mode=normal:all_opacity=0.35[s1];"
        "[s1][bloom]blend=all_mode=screen:all_opacity=0.45[s2];[s2][hal]blend=all_mode=screen:all_opacity=0.55[s3];"
        "[s3]eq=saturation=0.92:contrast=1.04:brightness=-0.01,colorbalance=rs=-0.02:gs=0.015:bs=0.03,format=yuv444p,noise=c0s=18:c0f=t+u,format=yuv420p")


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def first_mp4(folder: Path) -> Path:
    return next(p for p in sorted(folder.glob("*.mp4")) if p.name != "review.mp4" and not p.name.endswith("_mux.mp4"))


OVERRIDES: dict[str, Path] = {}  # take name -> explicit clip (e.g. an S2V singing take), set from --take


def take_path(lip: Path, name: str, tag: str | None) -> Path:
    if name in OVERRIDES:
        return OVERRIDES[name]
    if tag:
        cand = lip / name / tag / f"{name}_{tag}_mux.mp4"
        if cand.is_file():
            return cand
        print(f"  ! no {tag} take for {name}, using the H3 take")
    return lip / name / f"{name}_mux.mp4"


# ---------------------------------------------------------------- so I die (section time, 7.89 s in, 30.00 s out)
def sid_edl(variant: str, tag: str | None):
    B = R / "outputs/songs/so-i-die"; C = B / "clips"; L = C / "lipsync"
    IN, OUT_T = 7.89, 30.00
    # lip-sync takes start a little before their first word: (take, take start in section s)
    T = {"e2": ("sid_r3_esc_film2", 11.1), "g4": ("sid_r4_glance_film", 14.4), "e4": ("sid_r4_esc2_film", 17.55),
         "e5": ("sid_r4_esc3_film", 20.85), "g5": ("sid_r4_glance2_film", 20.85)}

    def ls(key, s0, s1):
        name, start = T[key]
        return (take_path(L, name, tag), s0 - start, s0, s1)

    walk = first_mp4(C / "sid_glance_walk_a"); esc = first_mp4(C / "sid_silent_escalator_wind"); train = first_mp4(C / "so-i-die_c04_trainpast")
    # G: the S2V takes (user-approved method), l9-l10 split so the held "away" is its own take driven by the lead-only
    # track. Slot keys l34/l56/l78/l9/l10 can be overridden with --take key=path (e.g. a world-mask composite).
    S2V = B / "singing"
    G = {"l34": OVERRIDES.get("l34", S2V / "sid_esc_move_b/sid_esc_move_b_push.mp4"),
         "l56": OVERRIDES.get("l56", S2V / "sid_l5l6_glance_b/sid_l5l6_glance_b_push.mp4"),
         "l78": OVERRIDES.get("l78", S2V / "sid_esc2_l7l8/sid_esc2_l7l8_push.mp4"),
         "l9": OVERRIDES.get("l9", S2V / "sid_l9_tired_esc3/sid_l9_tired_esc3_push.mp4"),
         "l10": OVERRIDES.get("l10", S2V / "sid_l10_hold_glance2/sid_l10_hold_glance2_push.mp4")}
    GS = {"l34": 11.1, "l56": 14.4, "l78": 17.55, "l9": 20.79, "l10": 22.5}  # take start times (section s)
    def g(key, s0, s1):
        return (G[key], s0 - GS[key], s0, s1)
    variants = {
        "G": [(walk, 5.167 - (11.34 - IN), IN, 11.34), g("l34", 11.34, 14.61), g("l56", 14.61, 17.77),
              g("l78", 17.77, 20.79), g("l9", 20.79, 22.57), g("l10", 22.57, 26.93), (train, 0, 26.93, OUT_T)],
        "E": [(walk, 5.167 - (11.34 - IN), IN, 11.34), ls("e2", 11.34, 14.61), ls("g4", 14.61, 17.77),
              ls("e4", 17.77, 20.79), ls("e5", 20.79, 26.93), (train, 0, 26.93, OUT_T)],
        "F": [(esc, 4.083 - (11.34 - IN), IN, 11.34), ls("e2", 11.34, 14.61), ls("g4", 14.61, 17.77),
              ls("e4", 17.77, 20.79), ls("g5", 20.79, 26.93), (train, 0, 26.93, OUT_T)],
    }
    return B, variants[variant], IN


def build_sid(variant: str, tag: str | None):
    B, edl, IN = sid_edl(variant, tag)
    label = f"{variant}_{tag}" if tag else variant
    out = B / "edit_v5" / label; out.mkdir(parents=True, exist_ok=True)
    parts, meta, f = [], [], 0
    for i, (src, cin, s0, s1) in enumerate(edl):
        n = round((s1 - s0) * FPS); dest = out / f"part{i}.mp4"
        if not src.is_file():
            raise SystemExit(f"missing {src}")
        ff("-ss", f"{max(0, cin):.4f}", "-i", src, "-vf",
           f"fps={FPS},scale=1344:768:flags=lanczos,setsar=1,tpad=stop_mode=clone:stop_duration=2,trim=end_frame={n},setpts=PTS-STARTPTS",
           "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16", dest)
        parts.append(dest); meta.append({"src": str(src.relative_to(R)), "in": round(cin, 4), "section": [s0, s1], "startFrame": f, "frames": n}); f += n
    (out / "edl.json").write_text(json.dumps(meta, indent=2))
    (out / "parts.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    ff("-f", "concat", "-safe", "0", "-i", out / "parts.txt", "-c", "copy", "-movflags", "+faststart", out / "silent.mp4")
    ff("-i", out / "silent.mp4", "-vf", FILM, "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-movflags", "+faststart", out / "silent_film.mp4")
    review = out / f"so_i_die_v5{label}_review.mp4"
    ff("-i", out / "silent_film.mp4", "-ss", f"{IN}", "-i", B / "so-i-die_section.wav", "-map", "0:v:0", "-map", "1:a:0",
       "-c:v", "copy", "-af", "apad", "-c:a", "aac", "-b:a", "256k", "-t", f"{f / FPS:.4f}", "-movflags", "+faststart", review)
    print(review, f"{f} frames = {f / FPS:.2f} s")
    return review


# ---------------------------------------------------------------- Playboi (section 12.12–30.11 s, 432 frames)
def build_pb(tag: str | None, variant: str = "v6"):
    B = R / "outputs/songs/playboi"; C = B / "clips"; L = C / "lipsync"
    IN = 12.12
    label = f"{variant}_{tag}" if tag else variant
    out = B / f"edit_{label}"; out.mkdir(parents=True, exist_ok=True)
    if variant == "v6":
        shots = [  # (src, in-frame, frames)
            (take_path(L, "pb_g_booth_hook", tag), 2, 107),   # 12.12–16.58  "You know I don't play, boy / Don't have all day, boy / You do what I say, boy"
            (first_mp4(C / "pb5_pool_smirk"), 36, 36),         # 16.58–18.08  "Uh-huh, uh-huh"
            (take_path(L, "pb_g_motel_play", tag), 0, 71),    # 18.08–21.04  "What was the play, boy / Don't have all day, boy"
            (first_mp4(C / "pb5_booth_smirk"), 0, 74),         # 21.04–24.12  "You see this shit / I'm gonna get back when I feel it"
            (first_mp4(C / "pb5_pool_smirk"), 72, 36), (first_mp4(C / "pb5_motel_wind"), 84, 36),
            (first_mp4(C / "pb5_booth_smirk"), 84, 36), (first_mp4(C / "pb5_booth_deadpan"), 84, 36),  # drop: quick cuts (v5)
        ]
    else:  # v7: lookbook v4 (user-approved stills) — S2V singing takes + H3 silent B-roll from the same stills
        S2V = B / "singing"; BR = B / "lookbook_v4/broll"
        def s2v(name): return S2V / name / f"{name}_push.mp4"
        def br(name): return first_mp4(BR / name)
        hook = OVERRIDES.get("hook", s2v("pb_hook_booth_deadpan"))
        shots = [
            (hook, 2, 107),                                    # 12.12–16.58  hook (booth deadpan; --take hook=... for the lean or car-hood alt)
            (s2v("pb_uhhuh_pool"), 2, 36),                     # 16.58–18.08  "Uh-huh, uh-huh" at the pool (take starts 16.50)
            (s2v("pb_play_booth_deadpan"), 0, 71),             # 18.08–21.04  "What was the play, boy / Don't have all day, boy" (take starts 18.10)
            (s2v("pb_seethis_carhood"), 1, 74),                # 21.04–24.12  "You see this shit / ... when I feel it" on the car hood (take starts 21.00)
            (br("br_hallway"), 12, 36), (br("br_mirror"), 6, 36), (br("br_pool"), 6, 36), (br("br_carhood"), 6, 36),  # drop: quick cuts, new B-roll
        ]
    parts, edl, f = [], [], 0
    for i, (src, start, n) in enumerate(shots):
        dest = out / f"part{i}.mp4"
        ff("-i", src, "-vf", f"fps={FPS},scale=1344:768:flags=lanczos,setsar=1,trim=start_frame={start}:end_frame={start + n},setpts=PTS-STARTPTS",
           "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16", dest)
        parts.append(dest); edl.append({"src": str(src.relative_to(R)), "inFrame": start, "startFrame": f, "frames": n}); f += n
    assert f == 432, f
    (out / "edl.json").write_text(json.dumps(edl, indent=2)); (out / "parts.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    ff("-f", "concat", "-safe", "0", "-i", out / "parts.txt", "-c", "copy", "-movflags", "+faststart", out / "silent.mp4")
    review = out / f"playboi_{label}_review.mp4"
    ff("-i", out / "silent.mp4", "-ss", f"{IN}", "-i", B / "playboi_section.wav", "-map", "0:v:0", "-map", "1:a:0",
       "-c:v", "copy", "-af", "apad", "-c:a", "aac", "-b:a", "256k", "-t", f"{f / FPS:.4f}", "-movflags", "+faststart", review)
    print(review, f"{f} frames")
    return review


def main():
    p = argparse.ArgumentParser()
    p.add_argument("song", choices=["so-i-die", "playboi"])
    p.add_argument("variants", nargs="*", help="so-i-die: E F (default E); playboi: v6 (old clips) or v7 (lookbook v4 S2V + B-roll)")
    p.add_argument("--tag", help="lip-sync pass tag to swap in (e.g. latentsync)")
    p.add_argument("--take", action="append", default=[], metavar="NAME=PATH",
                   help="replace a lip-sync take by name with an explicit clip, e.g. sid_r3_esc_film2=outputs/songs/so-i-die/singing/sid_esc_move_a/sid_esc_move_a_mux.mp4")
    p.add_argument("--label", help="output folder suffix (default: the tag, or 's2v' when --take is used)")
    a = p.parse_args()
    for spec in a.take:
        name, _, path = spec.partition("=")
        OVERRIDES[name] = (R / path).resolve() if not Path(path).is_absolute() else Path(path)
    if a.take and not a.tag:
        a.tag = a.label or "s2v"  # only used for the output folder name; take_path checks OVERRIDES first
    if a.song == "so-i-die":
        for v in a.variants or ["E"]:
            build_sid(v, a.tag)
    else:
        for v in a.variants or ["v6"]:
            build_pb(a.tag, v)


if __name__ == "__main__":
    main()
