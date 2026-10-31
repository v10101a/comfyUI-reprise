"""Hero project through the live API.

  server/.venv/bin/python scripts/content/hero_project.py create            # project + media + lyrics + matte + words
  server/.venv/bin/python scripts/content/hero_project.py apply <spec.json>  # surfaces (+track) + words + style, PUT
  server/.venv/bin/python scripts/content/hero_project.py export [tag]       # composite export -> outputs/hero/
Project id is kept in outputs/hero/project_id.txt.
"""
import json, shutil, subprocess, sys, time, uuid
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[2]; API = "http://127.0.0.1:8787"; OUT = ROOT / "outputs/hero"
PIDF = OUT / "project_id.txt"; FF = "/opt/homebrew/bin/ffmpeg"
c = httpx.Client(timeout=600)

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

def create():
    song = json.loads((ROOT / "outputs/concept-tests/song/song.json").read_text())
    p = c.post(f"{API}/api/projects", json={"name": "Typeset — Neon Rain (hero)"}).json(); pid = p["id"]; PIDF.write_text(pid); print("project", pid)
    for kind, path, mime in [("video", OUT / "hero_16x9.mp4", "video/mp4"), ("audio", ROOT / "outputs/concept-tests/song/neon_rain_00001.flac", "audio/flac")]:
        with path.open("rb") as fh: r = c.post(f"{API}/api/projects/{pid}/media", files={"file": (path.name, fh, mime)}, data={"kind": kind}); r.raise_for_status(); print(kind, r.json())
    p = c.get(f"{API}/api/projects/{pid}").json(); p["media"]["lyrics"] = song["lyrics"]; c.put(f"{API}/api/projects/{pid}", json=p).raise_for_status()
    for kind in ("words", "matte"):
        wait(c.post(f"{API}/api/projects/{pid}/analyze/{kind}", json={"language": "en"} if kind == "words" else {}).json(), kind)
    p = c.get(f"{API}/api/projects/{pid}").json(); (OUT / "project_seed.json").write_text(json.dumps(p, indent=2))
    for w in p["words"]: print(f"{w['start']:6.2f}-{w['end']:6.2f} {w['lineId']:>4} {w['text']}")

def apply(spec_path):
    pid = PIDF.read_text().strip(); spec = json.loads(Path(spec_path).read_text())
    p = c.get(f"{API}/api/projects/{pid}").json()
    old = {s["id"]: s for s in p.get("surfaces") or []}
    surfaces = []
    for s in spec.get("surfaces", []):
        o = old.get(s["id"]); same = o and o.get("corners") == s["corners"] and o.get("keyFrame") == s["keyFrame"]
        s = {k: v for k, v in s.items() if k not in ("noTrack", "track")} | ({"noTrack": True} if s.get("noTrack") else {})
        surfaces.append({**(o if same else {}), **s, **({"status": "drawn"} if not same else {})})
    p["surfaces"] = surfaces
    if spec.get("style"): p["style"] = {**p["style"], **spec["style"]}
    p["words"] = [{"id": w.get("id") or f"w{i:02d}", "lineId": w.get("lineId", f"l{i}"), "preset": "pop", "placement": "overlay", **w} for i, w in enumerate(spec["words"])]
    c.put(f"{API}/api/projects/{pid}", json=p).raise_for_status()
    for s in surfaces:
        if s.get("status") != "tracked" and not s.get("noTrack"):
            j = wait(c.post(f"{API}/api/projects/{pid}/surfaces/{s['id']}/track").json(), f"track {s['id']}"); print("   ", j.get("result"))
    p = c.get(f"{API}/api/projects/{pid}").json(); (OUT / "project.json").write_text(json.dumps(p, indent=2)); print("applied", len(p["words"]), "words")

def export(tag="v"):
    pid = PIDF.read_text().strip()
    j = wait(c.post(f"{API}/api/projects/{pid}/export", json={"layer": "composite", "formats": ["mp4"]}).json(), "export")
    files = (j.get("result") or {}).get("files") or {}; print(j.get("result"))
    rel = (files.get("mp4") or files.get("final.mp4")) if isinstance(files, dict) else None
    mp4 = ROOT / "data/projects" / pid / rel if rel else sorted((ROOT / "data/projects" / pid / "export").glob("*/final.mp4"), key=lambda q: q.stat().st_mtime)[-1]
    dst = OUT / f"iter/{tag}.mp4"; dst.parent.mkdir(exist_ok=True); shutil.copy(mp4, dst); shutil.copy(mp4, OUT / "hero_export.mp4"); print("->", dst)
    subprocess.run([str(ROOT / "scripts/content/sheet.sh"), str(dst), str(OUT / f"iter/{tag}_sheet.jpg"), "18", "6", "320"], check=True)

if __name__ == "__main__":
    {"create": lambda: create(), "apply": lambda: apply(sys.argv[2]), "export": lambda: export(*(sys.argv[2:3] or ["v"]))}[sys.argv[1]]()
