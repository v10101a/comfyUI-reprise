"""Fall For Me at 16:9 / 9:16 as separate Typeset projects (the 4:5 project 14ef9e95 is never touched).

  ~/ComfyUI/.venv/bin/python scripts/content/ffm_extend.py 16x9                      # extended footage -> work/ffm_v7_16x9.mp4
  ~/ComfyUI/.venv/bin/python scripts/content/ffm_extend.py 16x9 --matte outputs/ffm/work/key2_v7 outputs/ffm/work/key_16x9
  server/.venv/bin/python scripts/content/ffm_aspect.py create 16x9                 # project + media + matte + occupancy -> outputs/ffm/project_id_16x9.txt
  server/.venv/bin/python scripts/content/ffm_aspect.py spec 16x9 [base_spec]       # spec_v8.json re-laid out -> spec_v8_16x9.json, applied
  server/.venv/bin/python scripts/content/ffm_aspect.py export 16x9                 # -> outputs/ffm/iter/<aspect>.mp4

Layout: the original 4:5 frame sits unscaled-in-proportion in the middle (16:9: 912x1080 at x=504; 9:16: 1080x1280 at y=320).
Hooks (FALL / FOR ME, behind the stars) are mapped to exactly the same place on the stars, at the same pixel size.
Verse lines use the new space: 16:9 keeps them centred (they can run wider than the old frame); 9:16 moves them into the
new sky bands above/below the original frame, a bit larger than a straight remap.
"""
import json, shutil, sys, time
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[2]; API = "http://127.0.0.1:8787"; OUT = ROOT / "outputs/ffm"; WORK = OUT / "work"
SRC_PID = "14ef9e95-1d22-4bc1-8e42-5a1db01368ee"
GEOM = {"16x9": dict(W=1920, H=1080, w=912, h=1080, x0=504, y0=0), "9x16": dict(W=1080, H=1920, w=1080, h=1280, x0=0, y0=320)}
# 9:16 verse rows: original y -> new y (in the bands above/below the 4:5 frame)
VERSE_Y_9x16 = {.125: .07, .255: .135, .74: .865, .875: .93}
c = httpx.Client(timeout=900)
pidf = lambda a: OUT / f"project_id_{a}.txt"

def wait(job, label):
    t0 = time.time(); last = None
    while True:
        j = c.get(f"{API}/api/jobs/{job['id']}").json(); k = (j["status"], j.get("message"))
        if k != last: print(f"  [{label}] {time.time()-t0:5.0f}s {j['status']} {j.get('message') or ''}", flush=True); last = k
        if j["status"] in ("done", "failed"):
            if j["status"] == "failed": raise SystemExit(f"{label} failed: {j.get('message')}")
            return j
        time.sleep(2)

def create(a):
    src = c.get(f"{API}/api/projects/{SRC_PID}").json()
    p = c.post(f"{API}/api/projects", json={"name": f"Fall For Me — TD stars ({a.replace('x', ':')})"}).json(); pid = p["id"]; pidf(a).write_text(pid); print("project", pid)
    for kind, path, mime in [("video", WORK / f"ffm_v7_{a}.mp4", "video/mp4"), ("audio", WORK / "ffm_v7_audio.wav", "audio/wav")]:
        with path.open("rb") as fh: r = c.post(f"{API}/api/projects/{pid}/media", files={"file": (path.name, fh, mime)}, data={"kind": kind}); r.raise_for_status(); print(kind, r.json()["path"])
    d = ROOT / "data/projects" / pid / "analysis/matte"; d.mkdir(parents=True, exist_ok=True)
    key = WORK / f"key_{a}"
    for f in sorted(key.glob("fg_*.png")): shutil.copy(f, d / f.name)
    import subprocess
    subprocess.run(["/opt/homebrew/bin/ffmpeg", "-v", "error", "-y", "-framerate", "30", "-start_number", "1", "-i", str(d / "fg_%05d.png"), "-c:v", "libvpx-vp9",
                    "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "30", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", "-r", "30", str(d / "fg.webm")], check=True)
    p = c.get(f"{API}/api/projects/{pid}").json(); p["media"]["lyrics"] = src["media"]["lyrics"]; p["analysis"]["matte"] = "analysis/matte/"
    c.put(f"{API}/api/projects/{pid}", json=p).raise_for_status()
    wait(c.post(f"{API}/api/projects/{pid}/analyze/occupancy").json(), "occupancy")

def spec(a, base="outputs/ffm/spec_v8.json"):
    g = GEOM[a]; s = json.loads((ROOT / base).read_text()); k = g["h"] / g["H"]       # old-frame px -> new canvas height fraction
    for w in s["words"]:
        hook = s["lineMeta"][w["lineId"]]["hook"]; x, y = w["position"]["x"], w["position"]["y"]
        if hook or a == "16x9":
            w["position"] = {"x": round((g["x0"] + x * g["w"]) / g["W"], 4), "y": round((g["y0"] + y * g["h"]) / g["H"], 4)}
            w["style"]["fontSize"] = round(w["style"]["fontSize"] * k, 4)
        else:
            w["position"] = {"x": .5, "y": VERSE_Y_9x16.get(y, round((g["y0"] + y * g["h"]) / g["H"], 4))}
            w["style"]["fontSize"] = round(w["style"]["fontSize"] * k * 1.15, 4)
    s["style"]["fontSize"] = round(s["style"]["fontSize"] * k, 4)
    out = OUT / f"spec_v8_{a}.json"; out.write_text(json.dumps(s, indent=1)); print(out)
    pid = pidf(a).read_text().strip(); p = c.get(f"{API}/api/projects/{pid}").json()
    for key in ("style", "look", "lineMeta", "timing"):
        if key in s: p[key] = s[key]
    p["words"] = [{"preset": "pop", "placement": "overlay", **w} for w in s["words"]]
    c.put(f"{API}/api/projects/{pid}", json=p).raise_for_status()
    (OUT / f"project_{a}.json").write_text(json.dumps(c.get(f"{API}/api/projects/{pid}").json(), indent=2)); print("applied", len(p["words"]))

def export(a):
    pid = pidf(a).read_text().strip()
    j = wait(c.post(f"{API}/api/projects/{pid}/export", json={"layer": "composite", "formats": ["mp4"]}).json(), "export")
    rel = ((j.get("result") or {}).get("files") or {}).get("mp4")
    dst = OUT / f"iter/{a}.mp4"; shutil.copy(ROOT / "data/projects" / pid / rel, dst); print("->", dst)

if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2]
    {"create": lambda: create(a), "spec": lambda: spec(a, *sys.argv[3:4]), "export": lambda: export(a)}[cmd]()
