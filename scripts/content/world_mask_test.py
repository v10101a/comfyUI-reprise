"""Escalator-motion test with the Layers system: plate = the S2V singing take (person locked to the still), a media layer
= the old H3 take masked to the WORLD (outside the plate's matte) so its moving escalator/tunnel shows around her.

  server/.venv/bin/python scripts/content/world_mask_test.py --plate outputs/songs/so-i-die/singing/sid_esc_move_b/sid_esc_move_b_mux.mp4 \\
      --world outputs/songs/so-i-die/clips/lipsync/sid_r3_esc_film2/sid_r3_esc_film2_mux.mp4 --name esc_world_test [--scale 1.03]

Creates a scratch project on the local API, uploads both, runs the matte, sets the layer stack, exports a composite mp4
and prints its path. Nothing in existing projects is touched.
"""
import argparse
import json
import mimetypes
import time
from pathlib import Path

import httpx

API = "http://127.0.0.1:8787"
ROOT = Path(__file__).resolve().parents[2]


def wait_job(c: httpx.Client, job_id: str, what: str, timeout: float = 1800) -> dict:
    t0 = time.time()
    while True:
        j = c.get(f"{API}/api/jobs/{job_id}", timeout=30).json()
        st = j.get("status")
        if st in ("done", "succeeded", "completed", "error", "failed"):
            print(f"[{what}] {st} in {time.time() - t0:.0f} s", flush=True)
            if st in ("error", "failed"):
                raise SystemExit(json.dumps(j, indent=1)[:2000])
            return j
        if int(time.time() - t0) % 30 == 0:
            print(f"[{what}] {st} {j.get('progress')}: {j.get('message') or j.get('stage') or ''}", flush=True)
        if time.time() - t0 > timeout:
            raise SystemExit(f"{what} timed out")
        time.sleep(3)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--plate", type=Path, required=True)
    p.add_argument("--world", type=Path, required=True)
    p.add_argument("--name", default="world_mask_test")
    p.add_argument("--scale", type=float, default=1.03, help="world layer scale (hides the H3 person's drift behind the S2V silhouette)")
    p.add_argument("--world-in", type=float, default=0.0, help="world clip in-point (s) at project time 0")
    p.add_argument("--keep", action="store_true", help="keep the scratch project (default: leave it; nothing deletes projects)")
    a = p.parse_args()
    with httpx.Client(timeout=120) as c:
        pr = c.post(f"{API}/api/projects", json={"name": f"scratch · {a.name}"}).json()
        pid = pr["id"]
        print("project", pid, flush=True)
        with a.plate.open("rb") as fh:
            ref = c.post(f"{API}/api/projects/{pid}/media", data={"kind": "video"},
                         files={"file": (a.plate.name, fh, mimetypes.guess_type(a.plate.name)[0] or "video/mp4")}).json()
        print("plate", ref.get("duration"), ref.get("width"), ref.get("height"), flush=True)
        with a.world.open("rb") as fh:
            asset = c.post(f"{API}/api/projects/{pid}/assets", data={"name": "world (H3 take)"},
                           files={"file": (a.world.name, fh, "video/mp4")}).json()
        aid = asset["id"]
        print("world asset", aid, asset.get("duration"), flush=True)
        job = c.post(f"{API}/api/projects/{pid}/analyze/matte", json={}).json()
        wait_job(c, job["id"], "matte")
        proj = c.get(f"{API}/api/projects/{pid}").json()
        dur = float(proj["duration"])
        proj["layers"] = [
            {"id": "plate", "kind": "plate"},
            {"id": "world", "kind": "media", "name": "moving world (H3)", "assetId": aid, "start": 0.0, "in": a.world_in,
             "out": a.world_in + dur, "mask": "world", "graded": True, "transform": {"scale": a.scale}},
            {"id": "textb", "kind": "text", "which": "behind"},
            {"id": "subject", "kind": "subject"},
            {"id": "textf", "kind": "text", "which": "front"},
        ]
        proj["assets"] = proj.get("assets") or [asset]
        proj = c.put(f"{API}/api/projects/{pid}", json=proj).json()
        print("layers set:", [l["kind"] for l in proj.get("layers", [])], flush=True)
        job = c.post(f"{API}/api/projects/{pid}/export", json={"layer": "composite", "formats": ["mp4"]}).json()
        res = wait_job(c, job["id"], "export")
        print("export result:", json.dumps(res.get("result") or res, indent=1)[:800], flush=True)
        exp = ROOT / "data/projects" / pid / "export"
        mp4s = sorted(exp.glob("**/*.mp4"), key=lambda f: f.stat().st_mtime)
        print("composite ->", mp4s[-1] if mp4s else "(no mp4 found under export/)", flush=True)
        print("project id", pid, flush=True)


if __name__ == "__main__":
    main()
