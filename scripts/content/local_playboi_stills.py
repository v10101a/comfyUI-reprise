"""Playboi stills on the LOCAL Mac: Qwen-Image-Edit-2511 (int8, 4-step Lightning) with the real face photo as
<Picture 1> and an approved Playboi still as <Picture 2> (hair + outfit), rendering a brand-new scene at full size.

  ~/ComfyUI/.venv/bin/python scripts/content/local_playboi_stills.py <jobs.json> [--only a b] [--board]

jobs.json: {"face": png, "look": png, "width": 1344, "height": 768, "identity": "...", "shots": [{name, seed, prompt}]}
Outputs: <jobs dir>/raw/<name>/<name>_s<seed>.png, <jobs dir>/board.jpg
"""
import argparse, json, shutil, subprocess, sys, time, urllib.request, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMFY = "http://127.0.0.1:8188"
COMFY_INPUT = Path.home() / "ComfyUI/input/typeset/playboi_local"


def stage(p: Path) -> str:
    COMFY_INPUT.mkdir(parents=True, exist_ok=True)
    dst = COMFY_INPUT / f"{p.stem}_{uuid.uuid4().hex[:6]}{p.suffix}"
    shutil.copy(p, dst)
    return f"typeset/playboi_local/{dst.name}"


def graph(prompt: str, seed: int, face: str, look: str, w: int, h: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_image_edit_2511_int8_convrot.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "cpu"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": face}},
        "5": {"class_type": "LoadImage", "inputs": {"image": look}},
        "6": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["2", 0], "vae": ["3", 0], "image1": ["4", 0], "image2": ["5", 0], "prompt": prompt}},
        "7": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["2", 0], "vae": ["3", 0], "image1": ["4", 0], "image2": ["5", 0],
              "prompt": "smooth plastic skin, beauty filter, idol makeup, glossy red lips, anime, illustration, cgi, deformed hands, extra fingers, text, watermark, missing piercings, large breasts"}},
        "8": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "9": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors", "strength_model": 1.0}},
        "10": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["9", 0], "shift": 3.1}},
        "11": {"class_type": "KSampler", "inputs": {"model": ["10", 0], "seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
               "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["8", 0], "denoise": 1.0}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": prefix}},
    }


def run(g: dict, timeout: float) -> list[dict]:
    cid = uuid.uuid4().hex
    req = urllib.request.Request(f"{COMFY}/prompt", data=json.dumps({"prompt": g, "client_id": cid}).encode(), headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    if "prompt_id" not in r:
        raise SystemExit(f"submit failed: {r}")
    pid = r["prompt_id"]; t0 = time.time()
    while time.time() - t0 < timeout:
        h = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=30).read())
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise SystemExit(f"comfy error: {json.dumps(st)[:800]}")
            imgs = []
            for out in h[pid]["outputs"].values():
                imgs += out.get("images", [])
            if imgs:
                return imgs
        time.sleep(3)
    raise SystemExit("timeout")


def board(d: Path, shots: list[dict], cols: int = 3) -> Path:
    from PIL import Image, ImageDraw, ImageOps
    tiles = []
    for s in shots:
        for p in sorted((d / "raw" / s["name"]).glob("*.png")):
            tiles.append((f"{s['name']} {p.stem.split('_')[-1]}", p))
    if not tiles:
        return d / "board.jpg"
    cw, ch = 672, 384 + 24
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cw * cols, ch * rows), (16, 16, 16))
    dr = ImageDraw.Draw(sheet)
    for i, (name, p) in enumerate(tiles):
        im = ImageOps.contain(Image.open(p).convert("RGB"), (cw, 384))
        x, y = (i % cols) * cw, (i // cols) * ch
        sheet.paste(im, (x + (cw - im.width) // 2, y))
        dr.text((x + 6, y + 388), name, fill=(255, 255, 255))
    out = d / "board.jpg"; sheet.save(out, quality=88)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs", type=Path); ap.add_argument("--only", nargs="*"); ap.add_argument("--board", action="store_true")
    ap.add_argument("--seeds", type=int, default=1, help="extra seeds per shot (seed, seed+1, ...)")
    ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args()
    cfg = json.loads(a.jobs.read_text()); d = a.jobs.parent
    shots = [s for s in cfg["shots"] if not a.only or s["name"] in a.only]
    if not a.board:
        face = stage(ROOT / cfg["face"]); look = stage(ROOT / cfg["look"])
        for s in shots:
            out = d / "raw" / s["name"]; out.mkdir(parents=True, exist_ok=True)
            look_s = stage(ROOT / s["look"]) if s.get("look") else look
            for k in range(a.seeds):
                seed = s["seed"] + k
                dst = out / f"{s['name']}_s{seed}.png"
                if dst.exists():
                    print("skip", dst.name, flush=True); continue
                prompt = (cfg["identity"].strip() + " " + s["prompt"].strip()).strip()
                g = graph(prompt, seed, face, look_s, cfg.get("width", 1344), cfg.get("height", 768), f"typeset/pb_local/{s['name']}_s{seed}")
                (out / f"{s['name']}_s{seed}.workflow.json").write_text(json.dumps(g, indent=1))
                t0 = time.time()
                try:
                    imgs = run(g, a.timeout)
                except SystemExit as e:
                    print(f"[{s['name']} s{seed}] FAILED {e}", flush=True); continue
                src = Path.home() / "ComfyUI/output" / imgs[0].get("subfolder", "") / imgs[0]["filename"]
                shutil.copy(src, dst)
                print(f"[{s['name']} s{seed}] {time.time() - t0:.0f} s -> {dst}", flush=True)
    print("board ->", board(d, cfg["shots"]), flush=True)


if __name__ == "__main__":
    main()
