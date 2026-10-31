#!/usr/bin/env python3
"""Run an API-format ComfyUI workflow over the raw HTTP API and measure it.

Used by docs/model-eval.md. It records server-side execution time (from the execution_start /
execution_success timestamps ComfyUI writes into /history), wall time, queue wait, peak RSS of the
ComfyUI process and the minimum "free" memory seen while the job ran, downloads every output
(images / videos), optionally extracts evenly spaced frames from mp4 outputs, and appends one JSON
line per run to a log so tables can be built from it.

Examples
  python3 scripts/eval/comfy_run.py workflows/eval/ltx_t2v.api.json --tag t2v_768x448_49 \
      --set 5.width=768 --set 5.height=448 --set 5.length=49 --out docs/eval/raw/ltx --frames 4
  python3 scripts/eval/comfy_run.py wf.json --set 3.text="a long prompt" --seed 7 --seed-node 10

--set takes node.input=value; value is parsed as JSON when possible (numbers, true/false, [..]),
otherwise used as a string. --set-file node.input=@path reads the file's contents as the value.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid

HOST = os.environ.get("COMFY_HTTP", "http://127.0.0.1:8188")


def http(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HOST + path, data=data, method=method,
                                 headers={"content-type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def parse_value(v):
    if v.startswith("@"):
        with open(v[1:]) as f:
            return f.read()
    try:
        return json.loads(v)
    except Exception:
        return v


def comfy_pid():
    try:
        out = subprocess.run(["lsof", "-tiTCP:8188", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
        return int(out[0]) if out else None
    except Exception:
        return None


def rss_mb(pid):
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        return int(out) / 1024 if out else None
    except Exception:
        return None


def free_mb():
    """'free' as macOS reports it: free + inactive + speculative + purgeable pages (what can be reclaimed)."""
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
        page = 16384
        vals = {}
        for line in out.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                v = v.strip().rstrip(".")
                if v.isdigit():
                    vals[k.strip()] = int(v)
        if "page size of" in out.splitlines()[0]:
            page = int(out.splitlines()[0].split("page size of")[1].split()[0])
        reclaimable = sum(vals.get(k, 0) for k in ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable"))
        return reclaimable * page / 1e6
    except Exception:
        return None


def memory_pressure_pct():
    try:
        out = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            if "free percentage" in line:
                return int(line.split(":")[1].strip().rstrip("%"))
    except Exception:
        pass
    return None


class MemSampler(threading.Thread):
    def __init__(self, pid, interval=1.0, enabled=True):
        super().__init__(daemon=True)
        self.pid, self.interval, self.stop_flag = pid, interval, False
        self.enabled = enabled
        self.peak_rss = rss_mb(pid) if pid else None
        self.min_free = free_mb() if enabled else None
        self.start_rss = self.peak_rss

    def run(self):
        if not self.enabled:
            return
        while not self.stop_flag:
            if self.pid:
                r = rss_mb(self.pid)
                if r is not None and (self.peak_rss is None or r > self.peak_rss):
                    self.peak_rss = r
            f = free_mb()
            if f is not None and (self.min_free is None or f < self.min_free):
                self.min_free = f
            time.sleep(self.interval)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--set", action="append", default=[], help="node.input=value")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--seed-node", default=None, help="node id whose noise_seed/seed to set")
    ap.add_argument("--seed-input", default=None, help="input name for the seed (auto: noise_seed or seed)")
    ap.add_argument("--out", default="docs/eval/raw")
    ap.add_argument("--frames", type=int, default=0, help="extract N evenly spaced frames from each mp4 output")
    ap.add_argument("--log", default="docs/eval/results.jsonl")
    ap.add_argument("--timeout", type=float, default=3600)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    with open(args.workflow) as f:
        wf = json.load(f)
    for s in args.set:
        key, _, val = s.partition("=")
        node, _, inp = key.partition(".")
        if node not in wf:
            sys.exit(f"no node {node} in workflow")
        wf[node]["inputs"][inp] = parse_value(val)
    if args.seed is not None and args.seed_node:
        inp = args.seed_input or ("noise_seed" if "noise_seed" in wf[args.seed_node]["inputs"] else "seed")
        wf[args.seed_node]["inputs"][inp] = args.seed

    tag = args.tag or os.path.splitext(os.path.basename(args.workflow))[0]
    out_dir = os.path.join(args.out, tag)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)

    local_metrics = urllib.parse.urlparse(HOST).hostname in ("localhost", "127.0.0.1", "::1")
    pid = comfy_pid() if local_metrics else None
    sampler = MemSampler(pid, enabled=local_metrics)
    sampler.start()
    client_id = str(uuid.uuid4())
    t_submit = time.time()
    try:
        resp = http("POST", "/prompt", {"prompt": wf, "client_id": client_id})
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        sys.exit(f"POST /prompt failed {e.code}: {body[:2000]}")
    if "prompt_id" not in resp:
        sys.exit(f"submit error: {json.dumps(resp)[:2000]}")
    pid_ = resp["prompt_id"]
    if not args.quiet:
        print(f"[{tag}] submitted {pid_}")

    hist = None
    while time.time() - t_submit < args.timeout:
        h = http("GET", f"/history/{pid_}")
        if pid_ in h and h[pid_].get("status", {}).get("completed") is not None or (pid_ in h and h[pid_].get("status", {}).get("status_str") == "error"):
            hist = h[pid_]
            break
        time.sleep(0.5)
    t_done = time.time()
    sampler.stop_flag = True
    sampler.join(timeout=3)
    if hist is None:
        sys.exit("timeout waiting for job")

    status = hist.get("status", {})
    msgs = status.get("messages", [])
    ts = {}
    err = None
    for name, payload in msgs:
        if name in ("execution_start", "execution_success", "execution_error", "execution_interrupted"):
            ts[name] = payload.get("timestamp")
        if name == "execution_error":
            err = {k: payload.get(k) for k in ("node_id", "node_type", "exception_message")}
    exec_s = None
    if "execution_start" in ts and "execution_success" in ts:
        exec_s = (ts["execution_success"] - ts["execution_start"]) / 1000.0
    queue_wait = (ts["execution_start"] / 1000.0 - t_submit) if "execution_start" in ts else None

    outputs = []
    for node_id, out in hist.get("outputs", {}).items():
        for kind in ("images", "gifs", "videos"):
            for item in out.get(kind, []):
                fn, sub, typ = item.get("filename"), item.get("subfolder", ""), item.get("type", "output")
                if typ != "output":
                    continue
                q = urllib.parse.urlencode({"filename": fn, "subfolder": sub, "type": typ})
                dest = os.path.join(out_dir, fn)
                with urllib.request.urlopen(HOST + "/view?" + q, timeout=300) as r, open(dest, "wb") as f:
                    shutil.copyfileobj(r, f)
                outputs.append(dest)
                if args.frames and fn.lower().endswith((".mp4", ".webm", ".mov")):
                    n = args.frames
                    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                            "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", dest],
                                           capture_output=True, text=True).stdout.strip()
                    total = int(probe) if probe.isdigit() else 49
                    idxs = [round(i * (total - 1) / max(n - 1, 1)) for i in range(n)]
                    for i in idxs:
                        fdest = os.path.join(out_dir, f"{os.path.splitext(fn)[0]}_f{i:03d}.png")
                        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", dest, "-vf", f"select=eq(n\\,{i})",
                                        "-fps_mode", "vfr", "-frames:v", "1", fdest], capture_output=True, check=True)
                        outputs.append(fdest)

    rec = {
        "tag": tag, "workflow": args.workflow, "set": args.set, "seed": args.seed,
        "status": status.get("status_str"), "error": err,
        "exec_s": round(exec_s, 2) if exec_s is not None else None,
        "wall_s": round(t_done - t_submit, 2), "queue_wait_s": round(queue_wait, 2) if queue_wait is not None else None,
        "rss_start_mb": round(sampler.start_rss) if sampler.start_rss else None,
        "rss_peak_mb": round(sampler.peak_rss) if sampler.peak_rss else None,
        "min_free_mb": round(sampler.min_free) if sampler.min_free else None,
        "mem_free_pct_after": memory_pressure_pct() if local_metrics else None,
        "server": HOST,
        "outputs": outputs, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(args.log, "a") as f:
        f.write(json.dumps(rec) + "\n")
    if not args.quiet:
        print(json.dumps({k: v for k, v in rec.items() if k not in ("set", "workflow")}, indent=None))
    if status.get("status_str") == "error":
        sys.exit(2)


if __name__ == "__main__":
    main()
