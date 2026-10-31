"""Run an API-format ComfyUI workflow through the Comfy SDK against LOCAL ComfyUI (zero credits).

Path: this script -> comfy-sdk -> comfy-api-proxy (:8189) -> ComfyUI (:8188)

The SDK reads the target from the COMFY_BASE_URL env var (default: Comfy Cloud), so:
  export COMFY_BASE_URL=http://127.0.0.1:8189
  python run_local_workflow.py docs/workflows/smoke_test_api.json 3            # node "3" is the SaveImage
  python run_local_workflow.py docs/workflows/ltx_t2v_api.json 12 --prompt-node 3 --prompt "a fox running through snow"

Why we poll instead of client.run(): comfy-api-proxy 0.1.6 can report a job as "expired" for an
instant right after ComfyUI's execution_success event (the job has left the queue but is not yet in
/history). client.run() treats that as terminal and raises. Polling with a short grace period is robust.
"""
import argparse
import os
import sys
import time

from comfy_sdk import Comfy

TERMINAL = {"succeeded", "failed", "canceled"}

parser = argparse.ArgumentParser()
parser.add_argument("workflow", help="API-format workflow json (Export (API) in the UI)")
parser.add_argument("output_node", help="node id whose outputs to download")
parser.add_argument("--prompt-node", help="node id of a CLIPTextEncode to override")
parser.add_argument("--prompt", help="new positive prompt text")
parser.add_argument("--seed-node", help="node id of a sampler whose noise_seed to set (default: none)")
parser.add_argument("--seed", type=int, help="seed value; -1 = time-based (busts ComfyUI's cache)")
parser.add_argument("--out", default="outputs", help="download directory")
parser.add_argument("--timeout", type=float, default=900, help="seconds to wait for the job")
args = parser.parse_args()

os.environ.setdefault("COMFY_BASE_URL", "http://127.0.0.1:8189")
# The local proxy needs no key unless you started it with --token; the SDK still wants a string.
client = Comfy(api_key=os.environ.get("COMFY_API_KEY", "local"), timeout=60)

wf = client.workflows.from_file(args.workflow)
if args.prompt_node and args.prompt:
    wf.set_input(args.prompt_node, "text", args.prompt)
if args.seed_node and args.seed is not None:
    wf.set_input(args.seed_node, "noise_seed", int(time.time()) if args.seed < 0 else args.seed)

t0 = time.time()
job = client.submit(wf)
print(f"submitted {job.id} to {os.environ['COMFY_BASE_URL']}")

expired_strikes = 0
last = None
while time.time() - t0 < args.timeout:
    job.refresh()
    status = job.status
    if status != last:
        print(f"  {time.time() - t0:5.1f}s  {status}")
        last = status
    if status in TERMINAL:
        break
    if status == "expired":
        # Grace period for the proxy race described above; give up after ~5 s of consistent "expired".
        expired_strikes += 1
        if expired_strikes >= 10:
            break
    else:
        expired_strikes = 0
    time.sleep(0.5)

print(f"job {job.id} -> {job.status} in {time.time() - t0:.1f}s")
if job.status != "succeeded":
    print("error:", getattr(job, "error", None), file=sys.stderr)
    sys.exit(1)

os.makedirs(args.out, exist_ok=True)
outs = list(job.get_outputs(args.output_node))
if not outs:
    print("no outputs on node", args.output_node, file=sys.stderr)
    sys.exit(1)
for o in outs:
    path = os.path.join(args.out, o.name)
    o.to_file(path)
    print("saved", path)
