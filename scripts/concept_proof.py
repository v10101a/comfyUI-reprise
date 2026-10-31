"""Build a proof-of-concept Typeset project from a video + a word spec, through the live API, and make a contact sheet.

  server/.venv/bin/python scripts/concept_proof.py --video outputs/concept-tests/walk_night/clip.mp4 \
      --name "Proof: behind + anchor" --spec outputs/concept-tests/specs/walk_behind.json --out outputs/concept-tests/proofs/walk_behind

Spec JSON:
{
  "style": { ...partial TextStyle overrides for the project default... },
  "lyrics": "optional text",
  "analyze": ["matte", "words"],            # which analysis jobs to run (matte needed for behind/anchor)
  "words": [ {"text": "...", "start": 0.4, "end": 1.2, "lineId": "l0", "placement": "behind", "preset": "pop", "position": {"x": .5, "y": .5}, "style": {...}, "anchor": {"trackId": "person0", "dx": 0, "dy": -0.12}} ],
  "sheet": {"every": 12, "cols": 6}          # contact-sheet sampling
}
Words with no explicit words list + "words" in analyze → uses the transcription seeded by the server.
"""
import argparse
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8787"
FFMPEG = "/opt/homebrew/bin/ffmpeg"


def wait_job(client: httpx.Client, job_id: str, label: str, timeout: float = 3600) -> dict:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        j = client.get(f"{API}/api/jobs/{job_id}").json()
        key = (j.get("status"), j.get("message"))
        if key != last:
            print(f"  [{label}] {time.time() - t0:5.0f}s {j.get('status')} {j.get('progress') or ''} {j.get('message') or ''}")
            last = key
        if j.get("status") in ("done", "failed"):
            if j["status"] == "failed":
                raise SystemExit(f"{label} failed: {j.get('message')}")
            return j
        time.sleep(2)
    raise SystemExit(f"{label} timed out")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--audio", type=Path, help="optional separate audio file")
    ap.add_argument("--name", required=True)
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--project", help="reuse an existing project id (skips upload + analysis)")
    ap.add_argument("--skip-export", action="store_true")
    a = ap.parse_args()
    spec = json.loads(a.spec.read_text())
    a.out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=600) as c:
        if a.project:
            pid = a.project
            project = c.get(f"{API}/api/projects/{pid}").json()
            print("reusing project", pid)
        else:
            project = c.post(f"{API}/api/projects", json={"name": a.name}).json()
            pid = project["id"]
            print("project", pid)
            with a.video.open("rb") as fh:
                r = c.post(f"{API}/api/projects/{pid}/media", files={"file": (a.video.name, fh, "video/mp4")}, data={"kind": "video"})
            r.raise_for_status()
            print("uploaded video:", r.json())
            if a.audio:
                with a.audio.open("rb") as fh:
                    r = c.post(f"{API}/api/projects/{pid}/media", files={"file": (a.audio.name, fh, "audio/wav")}, data={"kind": "audio"})
                r.raise_for_status()
                print("uploaded audio:", r.json())
            project = c.get(f"{API}/api/projects/{pid}").json()
            if spec.get("lyrics"):
                project["media"]["lyrics"] = spec["lyrics"]
                project = c.put(f"{API}/api/projects/{pid}", json=project).json()
            for kind in spec.get("analyze", []):
                job = c.post(f"{API}/api/projects/{pid}/analyze/{kind}", json={}).json()
                wait_job(c, job["id"], kind)
            project = c.get(f"{API}/api/projects/{pid}").json()

        # apply style + words
        if spec.get("style"):
            project["style"] = {**project["style"], **spec["style"]}
        if spec.get("words"):
            words = []
            for i, w in enumerate(spec["words"]):
                words.append({"id": w.get("id") or f"w{i}-{uuid.uuid4().hex[:6]}", "text": w["text"], "start": float(w["start"]), "end": float(w["end"]),
                              "lineId": w.get("lineId", f"l{i}"), "placement": w.get("placement", "overlay"), "preset": w.get("preset", "pop"),
                              **({"position": w["position"]} if w.get("position") else {}), **({"anchor": w["anchor"]} if w.get("anchor") else {}),
                              **({"style": w["style"]} if w.get("style") else {})})
            project["words"] = words
        project = c.put(f"{API}/api/projects/{pid}", json=project).json()
        (a.out / "project.json").write_text(json.dumps(project, indent=2))
        tracks_rel = project.get("analysis", {}).get("tracks")
        if tracks_rel:
            tr = c.get(f"{API}/files/projects/{pid}/{tracks_rel}").json()
            (a.out / "tracks.json").write_text(json.dumps(tr))
            for t in tr.get("tracks", []):
                fr = t["frames"]
                print(f"track {t['id']} ({t['label']}): {len(fr)}/{tr.get('frames')} frames; first cx,cy=({fr[0]['cx']:.2f},{fr[0]['cy']:.2f}) last=({fr[-1]['cx']:.2f},{fr[-1]['cy']:.2f})" if fr else f"track {t['id']}: empty")
        if a.skip_export:
            return
        job = c.post(f"{API}/api/projects/{pid}/export", json={"layer": "composite", "formats": ["mp4"]}).json()
        res = wait_job(c, job["id"], "export")
        files = (res.get("result") or {}).get("files") or {}
        print("export files:", files)
        mp4_rel = files.get("final.mp4") if isinstance(files, dict) else None
        if not mp4_rel:
            # fall back: find the newest export dir
            exports = sorted((ROOT / "data/projects" / pid / "export").glob("*/final.mp4"), key=lambda p: p.stat().st_mtime)
            mp4 = exports[-1] if exports else None
        else:
            mp4 = ROOT / "data/projects" / pid / mp4_rel
        if mp4 and mp4.exists():
            shutil.copy(mp4, a.out / "final.mp4")
            sheet = spec.get("sheet", {"every": 12, "cols": 6})
            subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(mp4), "-vf", f"select='not(mod(n\\,{sheet['every']}))',scale=448:-1,tile={sheet['cols']}x{sheet.get('rows', 2)}", "-frames:v", "1", str(a.out / "sheet.jpg")], check=True)
            print("sheet:", a.out / "sheet.jpg")
        print("project id:", pid)


if __name__ == "__main__":
    main()
