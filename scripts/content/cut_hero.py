"""Cut the hero plates on the song's bar grid and mux the song.

  python3 scripts/content/cut_hero.py [--edl scripts/content/hero_edl.json] [--out outputs/hero/hero_16x9.mp4]

EDL: {"song": path, "song_in": 0, "fps": 24, "w": 1344, "h": 768, "fade_out": 0.8,
      "shots": [{"id", "src", "in", "start", "end", "note"}]}  -- start/end are song/timeline seconds; each shot
plays src from `in` for (end-start) s. Frame-exact: durations are snapped to whole frames on the timeline grid.
Writes the mp4 + <out>.edl.txt (CMX-ish listing).
"""
import argparse, json, subprocess, tempfile
from pathlib import Path
FF = "/opt/homebrew/bin/ffmpeg"
ap = argparse.ArgumentParser()
ap.add_argument("--edl", type=Path, default=Path("scripts/content/hero_edl.json"))
ap.add_argument("--out", type=Path, default=Path("outputs/hero/hero_16x9.mp4"))
a = ap.parse_args()
E = json.loads(a.edl.read_text()); fps = E.get("fps", 24); W, H = E.get("w", 1344), E.get("h", 768)
tmp = Path(tempfile.mkdtemp()); parts = []; lines = []
for i, s in enumerate(E["shots"]):
    f0, f1 = round(s["start"] * fps), round(s["end"] * fps); n = f1 - f0
    p = tmp / f"p{i:02d}.mp4"
    vf = f"scale={W}:{H}:flags=lanczos,setsar=1,fps={fps}" + (f",{s['vf']}" if s.get("vf") else "")
    subprocess.run([FF, "-v", "error", "-y", "-ss", f"{s['in']:.4f}", "-i", s["src"], "-an", "-vf", vf, "-frames:v", str(n),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p", str(p)], check=True)
    got = int(subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                              "stream=nb_read_frames", "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout.strip())
    if got < n:  # source ran short: pad by holding the last frame
        q = tmp / f"p{i:02d}b.mp4"
        subprocess.run([FF, "-v", "error", "-y", "-i", str(p), "-vf", f"tpad=stop_mode=clone:stop={n-got}", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(q)], check=True); p = q
    parts.append(p)
    lines.append(f"{i+1:03d}  {s['id']:<14} src {Path(s['src']).name:<34} in {s['in']:6.2f}  rec {f0/fps:6.2f}-{f1/fps:6.2f}  ({n} f)  {s.get('note','')}")
lst = tmp / "list.txt"; lst.write_text("".join(f"file '{p}'\n" for p in parts))
total = round(E["shots"][-1]["end"] * fps) / fps; fo = E.get("fade_out", 0.8)
a.out.parent.mkdir(parents=True, exist_ok=True)
subprocess.run([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-ss", str(E.get("song_in", 0)), "-i", E["song"],
                "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-r", str(fps),
                "-af", f"afade=t=out:st={total-fo:.3f}:d={fo}", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-t", f"{total:.4f}",
                "-movflags", "+faststart", str(a.out)], check=True)
(a.out.with_suffix(".edl.txt")).write_text(f"TITLE: {a.out.name}  fps {fps}  {W}x{H}  total {total:.2f}s  song {E['song']}\n" + "\n".join(lines) + "\n")
print("\n".join(lines)); print("wrote", a.out)
