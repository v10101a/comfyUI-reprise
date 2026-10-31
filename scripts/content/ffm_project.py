""""Fall For Me" lyric video (TouchDesigner footage) through the live API.

  server/.venv/bin/python scripts/content/ffm_project.py prep               # 30 fps working copy + synced audio cut
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
DUR = 37.1667         # 1115 frames at 30 fps (footage is 37.18 s at 60 fps)
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
    subprocess.run([FF, "-v", "error", "-y", "-i", SRC_VIDEO, "-t", str(DUR), "-vf", "fps=30", "-an", "-c:v", "libx264", "-preset", "slow",
                    "-crf", "16", "-g", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(WORK / "ffm_30.mp4")], check=True)
    subprocess.run([FF, "-v", "error", "-y", "-ss", str(OFFSET), "-t", str(DUR), "-i", SRC_SONG,
                    "-af", "afade=t=in:d=0.03,afade=t=out:st=36.4:d=0.75", "-c:a", "pcm_s24le", str(WORK / "ffm_audio.wav")], check=True)

def create():
    p = c.post(f"{API}/api/projects", json={"name": "Fall For Me — TD stars (lyric video)"}).json(); pid = p["id"]; PIDF.write_text(pid); print("project", pid)
    for kind, path, mime in [("video", WORK / "ffm_30.mp4", "video/mp4"), ("audio", WORK / "ffm_audio.wav", "audio/wav")]:
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
    for k in ("style", "look", "lineMeta"):
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
    {"prep": prep, "create": create, "words": words, "apply": lambda: apply(sys.argv[2]), "export": lambda: export(*(sys.argv[2:3] or ["v"]))}[sys.argv[1]]()
