"""Comfy Cloud readiness probe for Typeset's generation workflows.

  export TYPESET_CLOUD_API_KEY=comfyui-...        # platform.comfy.org -> API Keys -> New
  server/.venv/bin/python scripts/cloud_probe.py             # health + which workflows Cloud can run
  server/.venv/bin/python scripts/cloud_probe.py --smoke     # also run a 64x64 invert round trip (spends a few credits)
  server/.venv/bin/python scripts/cloud_probe.py --find minimax wan2.2 ltx   # list hosted model files matching words

Nothing here touches the local ComfyUI or the project store.
"""
import argparse
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

GEN_WORKFLOWS = ["scene_motion", "scene_body", "scene_performance", "h3_lipsync", "s2v", "s2v_motion", "s2v_performance", "ltx_i2v", "ltx_morph"]
MODEL_FIELDS = {"ckpt_name", "unet_name", "clip_name", "vae_name", "lora_name", "model_name", "audio_encoder_name"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smoke", action="store_true", help="run LoadImage->ImageInvert->SaveImage on Cloud end to end")
    p.add_argument("--find", nargs="*", metavar="WORD", help="print hosted model files whose name contains any WORD")
    p.add_argument("--studio", action="store_true", help="also check the Studio's saved workflows (data/workflows)")
    args = p.parse_args()

    key = os.environ.get("TYPESET_CLOUD_API_KEY") or os.environ.get("COMFY_CLOUD_API_KEY") or ""
    if not key.strip():
        print("Set TYPESET_CLOUD_API_KEY first (platform.comfy.org -> API Keys -> + New).", file=sys.stderr)
        return 2
    os.environ["TYPESET_CLOUD_API_KEY"] = key.strip()
    os.environ.setdefault("TYPESET_DATA_DIR", tempfile.mkdtemp(prefix="typeset-cloud-probe-"))
    from app.comfy import ComfyRunner, WorkflowRunError, remote_runner, remote_runner as _rr  # noqa: F401
    run = remote_runner
    assert run is not None and run.cloud, "remote_runner did not become the Cloud runner"

    print("== health")
    h = run.health()
    print(json.dumps(h, indent=2))
    if not h.get("comfyui"):
        print("Cloud did not answer /api/queue with this key. Paid plan with API access? Key copied whole?", file=sys.stderr)
        return 1

    print("== registry")
    t0 = time.monotonic()
    try:
        registry = run.object_info()
    except WorkflowRunError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"{len(registry)} node classes in {time.monotonic() - t0:.1f}s")
    hosted = sorted({v for node in registry.values() for name, spec in {**node.get("input", {}).get("required", {}), **node.get("input", {}).get("optional", {})}.items()
                     if name in MODEL_FIELDS and isinstance(spec, list) and spec and isinstance(spec[0], list) for v in spec[0] if isinstance(v, str)})
    print(f"{len(hosted)} model files selectable in loaders")
    for cls in ("MiniMaxH3ImageToVideo", "MiniMaxH3ReferenceToVideo", "MiniMaxH3AddGuide", "WanSoundImageToVideo", "VHS_VideoCombine", "BiRefNetRMBG", "LTXVImgToVideo", "TypesetRender"):
        print(f"  {'ok ' if cls in registry else '-- '} {cls}")

    if args.find:
        print("== hosted files matching", args.find)
        for name in hosted:
            if any(w.lower() in name.lower() for w in args.find):
                print("  ", name)

    print("== committed generation workflows")
    for name in GEN_WORKFLOWS:
        path = ROOT / "workflows" / f"{name}.api.json"
        if not path.is_file():
            continue
        report(run, name, json.loads(path.read_text()))

    if args.studio:
        print("== Studio workflows (data/workflows)")
        from app.workflows import api_graph
        for wf in sorted((ROOT / "data" / "workflows").glob("*/workflow.json")):
            data = json.loads(wf.read_text())
            graph = api_graph(data.get("graph") or data)
            if graph:
                report(run, f"{wf.parent.name} {data.get('name', '')}", graph)

    if args.smoke:
        print("== smoke: upload -> invert -> download")
        from PIL import Image
        with tempfile.TemporaryDirectory(prefix="typeset-cloud-smoke-") as tmp:
            tmp = Path(tmp)
            png = tmp / "reference.png"
            Image.new("RGB", (64, 64), (230, 30, 50)).save(png)
            (tmp / "smoke.api.json").write_text(json.dumps({
                "1": {"class_type": "LoadImage", "inputs": {"image": "reference.png"}},
                "2": {"class_type": "ImageInvert", "inputs": {"image": ["1", 0]}},
                "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0], "filename_prefix": "typeset/probe"}}}))
            (tmp / "smoke.inputs.json").write_text(json.dumps({"workflow": "smoke.api.json", "inputs": {"image": {"node": "1", "field": "image", "kind": "comfy_input_path"}},
                                                               "outputs": {"result": {"node": "3", "type": "image"}}}))
            t0 = time.monotonic()
            result = run.run("smoke", {"image": run.stage_image(png, "probe", "reference.png")}, tmp / "out", workflows_dir=tmp,
                             progress=lambda status, el: print(f"  {el:5.1f}s {status}"), poll_interval=2.0)
            out = result.first("result")
            px = Image.open(out).convert("RGB").getpixel((0, 0)) if out else None
            print(f"  job {result.job_id} {result.status} in {time.monotonic() - t0:.1f}s timing={result.timing} pixel={px} (expect ~(25,225,205))")
    return 0


def report(run, label: str, graph: dict) -> None:
    try:
        run.preflight_graph(graph)
        print(f"  ok  {label}")
    except WorkflowRunError as exc:
        text = str(exc)
        missing = text.split(": ", 1)[1] if ": " in text else text
        print(f"  --  {label}: {missing}")


if __name__ == "__main__":
    sys.exit(main())
