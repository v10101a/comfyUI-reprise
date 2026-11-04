"""Animate Playboi stills on the LOCAL Mac with LTX-Video 2B 0.9.8 distilled (image-to-video).

  ~/ComfyUI/.venv/bin/python scripts/content/local_playboi_motion.py <jobs.json> [--only a b]

jobs.json: {"width": 1344, "height": 768, "length": 49, "fps": 24, "shots": [{name, image, seed, prompt}]}
Outputs: <jobs dir>/clips/<name>/<name>_s<seed>.mp4 + workflow.json + run.json
"""
import argparse, json, shutil, sys, time, urllib.request, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/content"))
from local_playboi_stills import stage, run  # noqa: E402

NEG = ("low quality, worst quality, deformed, distorted, blurry, watermark, jittery, morphing face, changing face, "
       "extra fingers, smooth plastic skin, beauty filter, talking, mouthing words")


def graph(prompt: str, image: str, seed: int, w: int, h: int, n: int, fps: float, prefix: str) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "ltxv-2b-0.9.8-distilled.safetensors"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "ltxv", "device": "default"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["2", 0]}},
        "20": {"class_type": "LoadImage", "inputs": {"image": image}},
        "21": {"class_type": "LTXVPreprocess", "inputs": {"image": ["20", 0], "img_compression": 35}},
        "22": {"class_type": "LTXVImgToVideo", "inputs": {"positive": ["3", 0], "negative": ["4", 0], "vae": ["1", 2], "image": ["21", 0],
               "width": w, "height": h, "length": n, "batch_size": 1, "strength": 1.0}},
        "30": {"class_type": "PrimitiveFloat", "inputs": {"value": fps}},
        "6": {"class_type": "LTXVConditioning", "inputs": {"positive": ["22", 0], "negative": ["22", 1], "frame_rate": ["30", 0]}},
        "7": {"class_type": "ModelSamplingLTXV", "inputs": {"model": ["1", 0], "max_shift": 2.05, "base_shift": 0.95, "latent": ["22", 2]}},
        "8": {"class_type": "LTXVScheduler", "inputs": {"steps": 8, "max_shift": 2.05, "base_shift": 0.95, "stretch": True, "terminal": 0.1, "latent": ["22", 2]}},
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "10": {"class_type": "SamplerCustom", "inputs": {"model": ["7", 0], "add_noise": True, "noise_seed": seed, "cfg": 1.0, "positive": ["6", 0], "negative": ["6", 1],
               "sampler": ["9", 0], "sigmas": ["8", 0], "latent_image": ["22", 2]}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["1", 2]}},
        "12": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["11", 0], "frame_rate": ["30", 0], "loop_count": 0, "filename_prefix": prefix,
               "format": "video/h264-mp4", "pingpong": False, "save_output": True}},
    }


def run_video(g: dict, timeout: float) -> Path:
    cid = uuid.uuid4().hex
    req = urllib.request.Request(f"http://127.0.0.1:8188/prompt", data=json.dumps({"prompt": g, "client_id": cid}).encode(), headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    pid = r.get("prompt_id") or (_ for _ in ()).throw(SystemExit(f"submit failed: {r}"))
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = json.loads(urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}", timeout=30).read())
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise SystemExit(f"comfy error: {json.dumps(st)[:800]}")
            for out in h[pid]["outputs"].values():
                for v in out.get("gifs", []) + out.get("videos", []):
                    if v["filename"].endswith(".mp4"):
                        return Path.home() / "ComfyUI/output" / v.get("subfolder", "") / v["filename"]
        time.sleep(3)
    raise SystemExit("timeout")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs", type=Path); ap.add_argument("--only", nargs="*"); ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args()
    cfg = json.loads(a.jobs.read_text()); d = a.jobs.parent
    for s in cfg["shots"]:
        if a.only and s["name"] not in a.only:
            continue
        out = d / "clips" / s["name"]; out.mkdir(parents=True, exist_ok=True)
        dst = out / f"{s['name']}_s{s['seed']}.mp4"
        if dst.exists():
            print("skip", dst.name, flush=True); continue
        img = stage(ROOT / s["image"])
        g = graph(s["prompt"], img, s["seed"], s.get("width", cfg.get("width", 1344)), s.get("height", cfg.get("height", 768)),
                  s.get("length", cfg.get("length", 49)), cfg.get("fps", 24), f"typeset/pb_local_motion/{s['name']}_s{s['seed']}")
        (out / "workflow.json").write_text(json.dumps(g, indent=1))
        t0 = time.time()
        try:
            src = run_video(g, a.timeout)
        except SystemExit as e:
            print(f"[{s['name']}] FAILED {e}", flush=True); continue
        shutil.copy(src, dst)
        meta = {"engine": "LTX-Video 2B 0.9.8 distilled · local MPS", "prompt": s["prompt"], "seed": s["seed"], "source_image": s["image"],
                "width": g["22"]["inputs"]["width"], "height": g["22"]["inputs"]["height"], "length": g["22"]["inputs"]["length"], "seconds": round(time.time() - t0)}
        (out / "run.json").write_text(json.dumps(meta, indent=2))
        print(f"[{s['name']}] {meta['seconds']} s -> {dst}", flush=True)


if __name__ == "__main__":
    main()
