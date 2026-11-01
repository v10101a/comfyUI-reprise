"""Fall For Me v9 (user: start one bar before the first lyric, let the last "me" finish).
v9 = v8 minus its first 106 frames (3.533 s, the bar line at v8 3.545) and run 1.47 s longer, to v8 27.17 s, past the last "me" (vocal stem
silent at v8 ~27.15; next phrase 27.4). New media/matte/occupancy are cut from the same extended source; words shift by -3.533 s.
  server/.venv/bin/python scripts/content/ffm_v9.py prep|apply|export
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import ffm_project as F
CUT = 106; N = round(27.1667 * 30) - CUT          # 709 frames = 23.633 s
T = CUT / 30; F0 = F.V7_F0 + CUT

def prep():
    F.subprocess.run([F.FF, "-v", "error", "-y", "-i", str(F.WORK / "ffm_ext_30.mp4"), "-vf", f"trim=start_frame={F0}:end_frame={F0+N},setpts=PTS-STARTPTS",
                      "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-g", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(F.WORK / "ffm_v9_30.mp4")], check=True)
    d = N / 30
    F.subprocess.run([F.FF, "-v", "error", "-y", "-ss", f"{F.OFFSET+F.V7_A+T:.3f}", "-t", f"{d:.4f}", "-i", F.SRC_SONG,
                      "-af", "afade=t=in:d=0.03", "-c:a", "pcm_s24le", str(F.WORK / "ffm_v9_audio.wav")], check=True)
    pid = F.PIDF.read_text().strip()
    for kind, path, mime in [("video", F.WORK / "ffm_v9_30.mp4", "video/mp4"), ("audio", F.WORK / "ffm_v9_audio.wav", "audio/wav")]:
        with path.open("rb") as fh: r = F.c.post(f"{F.API}/api/projects/{pid}/media", files={"file": (path.name, fh, mime)}, data={"kind": kind}); r.raise_for_status(); print(kind, r.json())
    F.matte_shift(F.WORK / "key2", F0, N)

def apply():
    pid = F.PIDF.read_text().strip(); old = json.loads((F.OUT / "iter/v8_project_backup.json").read_text())
    p = F.c.get(f"{F.API}/api/projects/{pid}").json(); dur = p["duration"]
    for k in ("style", "look", "lineMeta", "frame", "shots", "surfaces"): p[k] = old[k]
    words = []
    for w in old["words"]:
        w = dict(w); w["start"] = round(w["start"] - T, 3)
        w["end"] = round(dur if w["end"] >= old["duration"] - .01 else w["end"] - T, 3)   # words held to the old end now hold to the new end
        words.append(w)
    p["words"] = words; p["timing"] = {**old["timing"], "vocalStart": round(old["timing"]["vocalStart"] - T, 3)}
    F.c.put(f"{F.API}/api/projects/{pid}", json=p).raise_for_status()
    p = F.c.get(f"{F.API}/api/projects/{pid}").json(); (F.OUT / "project.json").write_text(json.dumps(p, indent=2))
    print("applied", len(p["words"]), "words; dur", p["duration"], "first", min(w["start"] for w in p["words"]))

if __name__ == "__main__":
    {"prep": prep, "apply": apply, "export": lambda: F.export("v9")}[sys.argv[1]]()
