"""Submit MiniMax H3 jobs to the remote 4090 ComfyUI over its raw HTTP API and download the results.

Text-to-video (no first frame) or image-to-video (first frame already present in the remote input dir).
Based on workflows/eval/minimax_remote_i2v.api.json (the verified graph). Usage:

  server/.venv/bin/python scripts/remote_minimax.py --name walk --prompt "..." [--width 1344 --height 768 --length 124] [--first-frame typeset/x.png]
  server/.venv/bin/python scripts/remote_minimax.py --jobs jobs.json      # list of {name, prompt, ...}

Outputs: outputs/concept-tests/<name>/ (mp4 + workflow.json + history.json). A timeout does not cancel the remote job.
"""
import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE_GRAPH = ROOT / "workflows/eval/minimax_remote_i2v.api.json"


def build_graph(prompt: str, width: int, height: int, length: int, seed: int, first_frame: str | None, prefix: str) -> dict:
    g = json.loads(BASE_GRAPH.read_text())
    i2v = next(k for k, v in g.items() if v["class_type"] == "MiniMaxH3ImageToVideo")
    g[i2v]["inputs"].update({"prompt": prompt, "width": width, "height": height, "length": length})
    load_image = next((k for k, v in g.items() if v["class_type"] == "LoadImage"), None)
    if first_frame:
        g[load_image]["inputs"]["image"] = first_frame
    else:
        g[i2v]["inputs"].pop("first_frame", None)
        if load_image:
            del g[load_image]
    noise = next(k for k, v in g.items() if v["class_type"] == "RandomNoise")
    g[noise]["inputs"]["noise_seed"] = seed
    combine = next(k for k, v in g.items() if v["class_type"] == "VHS_VideoCombine")
    g[combine]["inputs"]["filename_prefix"] = prefix
    return g


def upload_image(base: str, local: Path, subfolder: str = "typeset/concept") -> str:
    """Upload a local image to the remote ComfyUI input dir; returns the path to use in LoadImage."""
    with local.open("rb") as fh:
        r = httpx.post(f"{base}/upload/image", files={"image": (local.name, fh, "image/png")},
                       data={"subfolder": subfolder, "overwrite": "true"}, timeout=120)
    r.raise_for_status()
    info = r.json()
    sub = info.get("subfolder") or subfolder
    return f"{sub}/{info['name']}" if sub else info["name"]


def run(base: str, graph: dict, out_dir: Path, timeout: float) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest()
    state_path = out_dir / "submission.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    if state and state["graph_sha256"] != digest:
        raise SystemExit(f"[{out_dir.name}] graph changed for an existing submission; use a new output directory")

    def save_state():
        tmp = state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(state_path)

    t0 = time.monotonic()
    deadline = t0 + timeout

    def get(url: str, **kwargs):
        """Reads are safe to retry; submissions are deliberately never retried."""
        while True:
            try:
                response = httpx.get(url, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPError as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in (408, 429, 500, 502, 503, 504):
                    raise
                if time.monotonic() >= deadline:
                    raise SystemExit(f"[{out_dir.name}] connection timed out; resume prompt {pid} from {state_path}") from exc
                print(f"[{out_dir.name}] connection interrupted; retrying existing prompt {pid}", flush=True)
                time.sleep(5)

    (out_dir / "workflow.json").write_text(json.dumps(graph, indent=2))
    if state:
        pid = state["prompt_id"]
        if state.get("status") == "rejected":
            raise SystemExit(f"[{out_dir.name}] previous submission was rejected: {state.get('error')}")
        print(f"[{out_dir.name}] resuming {pid}", flush=True)
    else:
        pid = str(uuid.uuid4())
        state = {"prompt_id": pid, "graph_sha256": digest, "status": "submitting"}
        save_state()  # persist before POST: a lost response must never cause a duplicate render
        try:
            r = httpx.post(f"{base}/prompt", json={"prompt": graph, "prompt_id": pid, "client_id": pid}, timeout=60)
        except httpx.HTTPError as exc:
            state.update(status="unknown", error=str(exc))
            save_state()
            raise SystemExit(f"[{out_dir.name}] submission response lost; inspect/resume prompt {pid}, do not resubmit blindly") from exc
        if r.status_code != 200:
            # A server error may arrive after acceptance. Only a definitive
            # client error is a rejection; ambiguous responses retain the ID.
            state.update(status="rejected" if 400 <= r.status_code < 500 else "unknown", error=r.text[:1500])
            save_state()
            raise SystemExit(f"submission response ({r.status_code}): {r.text[:1500]}; retained prompt {pid}")
        state["status"] = "submitted"
        save_state()
        print(f"[{out_dir.name}] submitted {pid}", flush=True)
    while time.monotonic() < deadline:
        h = get(f"{base}/history/{pid}", timeout=30).json()
        if pid in h:
            break
        time.sleep(5)
    else:
        raise SystemExit(f"[{out_dir.name}] timed out after {timeout}s; job may still be running remotely")
    entry = h[pid]
    (out_dir / "history.json").write_text(json.dumps(entry, indent=2))
    status = entry.get("status", {}).get("status_str")
    print(f"[{out_dir.name}] {status} in {time.monotonic() - t0:.0f}s", flush=True)
    if status != "success":
        state["status"] = "failed"
        save_state()
        raise SystemExit(json.dumps(entry.get("status"), indent=2)[:2000])
    saved = []
    for node_out in entry.get("outputs", {}).values():
        for key in ("gifs", "images", "videos"):
            for f in node_out.get(key, []) or []:
                if f.get("type") != "output":
                    continue
                params = {"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": "output"}
                data = get(f"{base}/view", params=params, timeout=600).content
                dest = out_dir / f["filename"]
                tmp = dest.with_name(dest.name + ".part")
                tmp.write_bytes(data)
                tmp.replace(dest)
                saved.append(str(dest))
    result = {"prompt_id": pid, "seconds": round(time.monotonic() - t0), "files": saved}
    state.update(status="downloaded", files=saved)
    save_state()
    print(f"[{out_dir.name}] saved {saved}", flush=True)
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://100.104.17.103:8188")
    p.add_argument("--name")
    p.add_argument("--prompt")
    p.add_argument("--width", type=int, default=1344)
    p.add_argument("--height", type=int, default=768)
    p.add_argument("--length", type=int, default=124)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--first-frame", help="path relative to the remote ComfyUI input dir")
    p.add_argument("--upload-first-frame", type=Path, help="local image to upload to the remote input dir and use as first frame")
    p.add_argument("--jobs", type=Path, help="JSON list of job dicts (name, prompt, width, height, length, seed, first_frame)")
    p.add_argument("--out", type=Path, default=ROOT / "outputs/concept-tests")
    p.add_argument("--timeout", type=float, default=1500)
    a = p.parse_args()

    jobs = json.loads(a.jobs.read_text()) if a.jobs else [{"name": a.name, "prompt": a.prompt}]
    results = []
    for j in jobs:
        if not j.get("name") or not j.get("prompt"):
            sys.exit("each job needs name and prompt")
        local_frame = Path(j["upload_first_frame"]) if j.get("upload_first_frame") else a.upload_first_frame
        if local_frame:
            j["first_frame"] = upload_image(a.base, local_frame)
            print(f"[{j['name']}] uploaded first frame -> {j['first_frame']}")
        graph = build_graph(j["prompt"], j.get("width", a.width), j.get("height", a.height), j.get("length", a.length),
                            j.get("seed", a.seed), j.get("first_frame", a.first_frame), f"concept/{j['name']}")
        results.append({"name": j["name"], **run(a.base, graph, a.out / j["name"], a.timeout)})
    (a.out / "last_run.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
