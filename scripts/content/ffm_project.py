""""Fall For Me" lyric video (TouchDesigner footage) through the live API.

  server/.venv/bin/python scripts/content/ffm_project.py prep               # 30 fps extended cut (ffm-6 + ffm-5) + synced audio
  server/.venv/bin/python scripts/content/ffm_project.py remedia            # swap the project media to that cut
  server/.venv/bin/python scripts/content/ffm_project.py prep7              # v7: trimmed cut (frames 150+, audio from clip 11.45 s)
  server/.venv/bin/python scripts/content/ffm_project.py remedia v7; ... matte_shift outputs/ffm/work/key2   # v7 media + shifted matte/occupancy
  server/.venv/bin/python scripts/content/ffm_project.py matte <key_dir>    # install key matte + occupancy
  server/.venv/bin/python scripts/content/ffm_project.py create             # project + media + lyrics + words + matte
  server/.venv/bin/python scripts/content/ffm_project.py apply <spec.json>  # words/look/lineMeta from a spec, PUT
  server/.venv/bin/python scripts/content/ffm_project.py export [tag]       # composite MP4 -> outputs/ffm/
Project id is kept in outputs/ffm/project_id.txt.
"""
import json, shutil, subprocess, sys, time
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[2]; API = "http://127.0.0.1:8787"; OUT = ROOT / "outputs/ffm"; WORK = OUT / "work"
PIDF = OUT / "project_id.txt"; FF = "/opt/homebrew/bin/ffmpeg"
SRC_VIDEO = "/Users/lh1783/Desktop/TD/0831/ffm-6.mov"
SRC_SONG = "/Users/lh1783/Downloads/v10101a/fall for me master 2.wav"
OFFSET = 126.857      # ffm-clip-1.wav cross-correlated against the master (FFT xcorr, re-checked: 126.8571 s)
# v4 (extended): ffm-6 to 35.7 s, 0.5 s dissolve (centred on the beat at master 162.76) into ffm-5 from 28.33 s, which ends
# just before ffm-5's own loop. ffm-6 loops back to its title at 36.2 s. The video ends on the phrase boundary at master
# 172.6 s, before "don't leave a mark" (172.7 s).
SRC_VIDEO2 = "/Users/lh1783/Desktop/TD/0831/ffm-5.mov"; JOIN = 35.7; JOIN_SRC2 = 28.33; XFADE = .5
DUR = 45.7333         # 1372 frames at 30 fps
LYRICS = """Stop thinking
For a minute
The stars are blinking
They're waiting
Come to me
A little silly
I'll make you happy
I'll make you
Fall for me"""
c = httpx.Client(timeout=900)

def wait(job, label):
    t0 = time.time(); last = None
    while True:
        j = c.get(f"{API}/api/jobs/{job['id']}").json()
        k = (j["status"], j.get("message"))
        if k != last: print(f"  [{label}] {time.time()-t0:5.0f}s {j['status']} {j.get('message') or ''}", flush=True); last = k
        if j["status"] in ("done", "failed"):
            if j["status"] == "failed": raise SystemExit(f"{label} failed: {j.get('message')}")
            return j
        time.sleep(2)

def prep():
    WORK.mkdir(parents=True, exist_ok=True)
    fc = (f"[0:v]fps=30,settb=AVTB,setpts=PTS-STARTPTS[a];[1:v]fps=30,settb=AVTB,setpts=PTS-STARTPTS[b];"
          f"[a][b]xfade=transition=fade:duration={XFADE}:offset={JOIN},trim=end_frame={round(DUR*30)},format=yuv420p[v]")
    subprocess.run([FF, "-v", "error", "-y", "-t", "36.2", "-i", SRC_VIDEO, "-ss", str(JOIN_SRC2), "-t", "10.1", "-i", SRC_VIDEO2,
                    "-filter_complex", fc, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-g", "30",
                    "-movflags", "+faststart", str(WORK / "ffm_ext_30.mp4")], check=True)
    subprocess.run([FF, "-v", "error", "-y", "-ss", str(OFFSET), "-t", str(DUR), "-i", SRC_SONG,
                    "-af", f"afade=t=in:d=0.03,afade=t=out:st={DUR-.6:.2f}:d=0.6", "-c:a", "pcm_s24le", str(WORK / "ffm_ext_audio.wav")], check=True)

# v7 (user: drop the instrumental intro). The audio starts at clip 11.45 s (master 138.307), with a 0.2 s fade-in that ends
# on the beat at 11.65. The video starts at cut frame 150 (5.0 s), so the footage runs 6.45 s ahead of v6 relative to the audio
# (the TD stars aren't music-synced). It ends 0.5 s after the v6 end-beat (clip 37.16 = v7 25.71): 771 frames = 25.70 s.
V7_A = 11.45; V7_F0 = 150; V7_N = 771

def prep7():
    subprocess.run([FF, "-v", "error", "-y", "-i", str(WORK / "ffm_ext_30.mp4"), "-vf", f"trim=start_frame={V7_F0}:end_frame={V7_F0+V7_N},setpts=PTS-STARTPTS",
                    "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-g", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(WORK / "ffm_v7_30.mp4")], check=True)
    d = V7_N / 30
    subprocess.run([FF, "-v", "error", "-y", "-ss", f"{OFFSET+V7_A:.3f}", "-t", f"{d:.4f}", "-i", SRC_SONG,
                    "-af", f"afade=t=in:d=0.2,afade=t=out:st={d-.5:.3f}:d=0.5", "-c:a", "pcm_s24le", str(WORK / "ffm_v7_audio.wav")], check=True)

def matte_shift(key_dir, f0=V7_F0, n=V7_N):
    """Install the existing key matte shifted by f0 frames (new fg_00001 = old fg_{f0+1}) and slice occupancy.json the same way
    (no re-key, no occupancy job)."""
    pid = PIDF.read_text().strip(); pd = ROOT / "data/projects" / pid; d = pd / "analysis/matte"
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    for i in range(1, n + 1): shutil.copy(Path(key_dir) / f"fg_{i+f0:05d}.png", d / f"fg_{i:05d}.png")
    subprocess.run([FF, "-v", "error", "-y", "-framerate", "30", "-start_number", "1", "-i", str(d / "fg_%05d.png"), "-c:v", "libvpx-vp9",
                    "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "30", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4",
                    "-r", "30", str(d / "fg.webm")], check=True)
    occ = json.loads((OUT / "work/occupancy_ext.json").read_text()); occ["frames"] = occ["frames"][f0:f0 + n]
    (pd / "analysis/occupancy.json").write_text(json.dumps(occ))
    p = c.get(f"{API}/api/projects/{pid}").json(); p["analysis"]["matte"] = "analysis/matte/"; p["analysis"]["occupancy"] = "analysis/occupancy.json"
    c.put(f"{API}/api/projects/{pid}", json=p).raise_for_status(); print("matte", n, "frames from", f0, "; occupancy", len(occ["frames"]))

def remedia(tag="ext"):
    """Swap the project's media to the extended cut, or `remedia v7` (clears the matte; re-key + occupancy afterwards, or matte_shift)."""
    pid = PIDF.read_text().strip()
    v, a = ("ffm_v7_30.mp4", "ffm_v7_audio.wav") if tag == "v7" else ("ffm_ext_30.mp4", "ffm_ext_audio.wav")
    for kind, path, mime in [("video", WORK / v, "video/mp4"), ("audio", WORK / a, "audio/wav")]:
        with path.open("rb") as fh: r = c.post(f"{API}/api/projects/{pid}/media", files={"file": (path.name, fh, mime)}, data={"kind": kind}); r.raise_for_status(); print(kind, r.json())

def matte(key_dir):
    """Install a key matte (fg_%05d.png) as analysis/matte/ (+ VP9-alpha fg.webm like server/app/media.py), then occupancy."""
    pid = PIDF.read_text().strip(); d = ROOT / "data/projects" / pid / "analysis/matte"
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    for f in sorted(Path(key_dir).glob("fg_*.png")): shutil.copy(f, d / f.name)
    subprocess.run([FF, "-v", "error", "-y", "-framerate", "30", "-start_number", "1", "-i", str(d / "fg_%05d.png"), "-c:v", "libvpx-vp9",
                    "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "30", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4",
                    "-r", "30", str(d / "fg.webm")], check=True)
    p = c.get(f"{API}/api/projects/{pid}").json(); p["analysis"]["matte"] = "analysis/matte/"; c.put(f"{API}/api/projects/{pid}", json=p).raise_for_status()
    q = httpx.get("http://127.0.0.1:8188/queue", timeout=10).json(); print("comfy queue", len(q["queue_running"]), len(q["queue_pending"]))
    wait(c.post(f"{API}/api/projects/{pid}/analyze/occupancy").json(), "occupancy")

def create():
    p = c.post(f"{API}/api/projects", json={"name": "Fall For Me — TD stars (lyric video)"}).json(); pid = p["id"]; PIDF.write_text(pid); print("project", pid)
    for kind, path, mime in [("video", WORK / "ffm_ext_30.mp4", "video/mp4"), ("audio", WORK / "ffm_ext_audio.wav", "audio/wav")]:
        with path.open("rb") as fh: r = c.post(f"{API}/api/projects/{pid}/media", files={"file": (path.name, fh, mime)}, data={"kind": kind}); r.raise_for_status(); print(kind, r.json())
    p = c.get(f"{API}/api/projects/{pid}").json(); p["media"]["lyrics"] = LYRICS; c.put(f"{API}/api/projects/{pid}", json=p).raise_for_status()
    words()
    if "--no-matte" not in sys.argv: wait(c.post(f"{API}/api/projects/{pid}/analyze/matte", json={}).json(), "matte")

def words():
    pid = PIDF.read_text().strip()
    wait(c.post(f"{API}/api/projects/{pid}/analyze/words", json={"language": "en"}).json(), "words")
    p = c.get(f"{API}/api/projects/{pid}").json(); (OUT / "project_seed.json").write_text(json.dumps(p, indent=2))
    for w in p["words"]: print(f"{w['start']:6.2f}-{w['end']:6.2f} {w['lineId']:>4} {w['text']}")

def apply(spec_path):
    pid = PIDF.read_text().strip(); spec = json.loads(Path(spec_path).read_text())
    p = c.get(f"{API}/api/projects/{pid}").json()
    for k in ("style", "look", "lineMeta", "timing"):
        if k in spec: p[k] = spec[k]
    p["words"] = [{"id": w.get("id") or f"w{i:02d}", "preset": "pop", "placement": "overlay", **w} for i, w in enumerate(spec["words"])]
    c.put(f"{API}/api/projects/{pid}", json=p).raise_for_status()
    p = c.get(f"{API}/api/projects/{pid}").json(); (OUT / "project.json").write_text(json.dumps(p, indent=2)); print("applied", len(p["words"]), "words")

def export(tag="v"):
    pid = PIDF.read_text().strip()
    j = wait(c.post(f"{API}/api/projects/{pid}/export", json={"layer": "composite", "formats": ["mp4"]}).json(), "export")
    files = (j.get("result") or {}).get("files") or {}; print(j.get("result"))
    rel = files.get("final.mp4") if isinstance(files, dict) else None
    mp4 = ROOT / "data/projects" / pid / rel if rel else sorted((ROOT / "data/projects" / pid / "export").glob("*/final.mp4"), key=lambda q: q.stat().st_mtime)[-1]
    dst = OUT / f"iter/{tag}.mp4"; dst.parent.mkdir(exist_ok=True); shutil.copy(mp4, dst); print("->", dst)
    subprocess.run([str(ROOT / "scripts/content/sheet.sh"), str(dst), str(OUT / f"iter/{tag}_sheet.jpg"), "16", "8", "270"], check=True)

if __name__ == "__main__":
    {"prep": prep, "prep7": prep7, "remedia": lambda: remedia(*sys.argv[2:3]), "matte_shift": lambda: matte_shift(sys.argv[2]), "matte": lambda: matte(sys.argv[2]), "create": create, "words": words, "apply": lambda: apply(sys.argv[2]), "export": lambda: export(*(sys.argv[2:3] or ["v"]))}[sys.argv[1]]()
