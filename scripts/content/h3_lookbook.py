"""Lookbook stills with the approved Fall For Me recipe: MiniMax H3 reference-to-video on the 4090 with two references
(<Picture 1> = the real face photo, <Picture 2> = the hair reference, ref_image_size max), a short clip, and a few
frames of it saved as PNG stills. Then a labelled board for picking.

  server/.venv/bin/python scripts/content/h3_lookbook.py outputs/songs/playboi/lookbook_v4/jobs.json [--only a b] [--board]

jobs.json: {"ref": face.png, "ref2": hair.png, "width": 1344, "height": 768, "length": 39, "frames": [12, 24, 38],
            "identity": "<text that describes the person; the per-shot prompt is appended>",
            "shots": [{"name": ..., "seed": ..., "prompt": "..."}, ...]}
Outputs: <jobs dir>/raw/<name>/<name>_fNNN_00001_.png, <jobs dir>/board.jpg (one frame per shot, labelled).
Submits one job at a time and waits for the shared remote queue to be empty before each (other agents use the GPU).
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/content"))
from remote_minimax import run, upload_image  # noqa: E402
from minimax_ref import build as ref_build  # noqa: E402

BASE = "http://100.104.17.103:8188"


def wait_idle(base: str) -> None:
    while True:
        try:
            q = httpx.get(f"{base}/queue", timeout=30).json()
            if not q["queue_running"] and not q["queue_pending"]:
                return
        except httpx.HTTPError:
            pass
        time.sleep(10)


def still_graph(cfg: dict, shot: dict, ref: str, ref2: str, prefix: str) -> dict:
    prompt = (cfg.get("identity", "").strip() + " " + shot["prompt"].strip()).strip()
    g = ref_build(prompt, shot.get("seed", 7), ref, prefix, width=cfg.get("width", 1344), height=cfg.get("height", 768),
                  length=cfg.get("length", 39), ref_size="max")
    g["50"] = {"class_type": "LoadImage", "inputs": {"image": ref2}}
    g["6"]["inputs"]["ref_images.ref_image_2"] = ["50", 0]
    for k in ("14", "15"):  # no audio decode, no mp4: frames only
        g.pop(k, None)
    for i, f in enumerate(cfg.get("frames", [12, 24, 38])):
        g[f"40{i}"] = {"class_type": "ImageFromBatch", "inputs": {"image": ["12", 0], "batch_index": f, "length": 1}}
        g[f"41{i}"] = {"class_type": "SaveImage", "inputs": {"images": [f"40{i}", 0], "filename_prefix": f"{prefix}_f{f:03d}"}}
    return g


def board(jobs_dir: Path, shots: list[dict], frame_pick: int = 1, cols: int = 4) -> Path:
    """One frame per shot (the middle one by default), labelled with the shot name, in a grid."""
    tiles = []
    for s in shots:
        pngs = sorted((jobs_dir / "raw" / s["name"]).glob("*.png"))
        if not pngs:
            continue
        src = pngs[min(frame_pick, len(pngs) - 1)]
        tile = jobs_dir / "board_tiles" / f"{s['name']}.jpg"
        tile.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", "scale=672:-1", str(tile)], check=True)
        tiles.append((s["name"], tile))
    if not tiles:
        return jobs_dir / "board.jpg"
    # labels with PIL (ffmpeg here has no drawtext)
    from PIL import Image, ImageDraw
    ims = []
    for name, t in tiles:
        im = Image.open(t).convert("RGB")
        d = ImageDraw.Draw(im)
        d.rectangle([0, im.height - 28, 10 + 9 * len(name), im.height], fill=(0, 0, 0))
        d.text((6, im.height - 24), name, fill=(255, 255, 255))
        ims.append(im)
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, h * rows), (16, 16, 16))
    for i, im in enumerate(ims):
        sheet.paste(im.resize((w, h)), ((i % cols) * w, (i // cols) * h))
    out = jobs_dir / "board.jpg"
    sheet.save(out, quality=88)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("jobs", type=Path)
    p.add_argument("--only", nargs="*")
    p.add_argument("--base", default=BASE)
    p.add_argument("--board", action="store_true", help="only rebuild the board from existing stills")
    p.add_argument("--timeout", type=float, default=1200)
    a = p.parse_args()
    cfg = json.loads(a.jobs.read_text())
    d = a.jobs.parent
    shots = [s for s in cfg["shots"] if not a.only or s["name"] in a.only]
    if not a.board:
        sub = cfg.get("subfolder", "typeset/lookbook")
        ref = upload_image(a.base, ROOT / cfg["ref"], sub)
        ref2 = upload_image(a.base, ROOT / cfg["ref2"], sub)
        for s in shots:
            out = d / "raw" / s["name"]
            if out.exists() and list(out.glob("*.png")):
                print(f"skip {s['name']} (done)", flush=True)
                continue
            out.mkdir(parents=True, exist_ok=True)
            wait_idle(a.base)
            g = still_graph(cfg, s, ref, ref2, f"{cfg.get('prefix', 'lookbook')}/{s['name']}")
            t0 = time.time()
            try:
                run(a.base, g, out, a.timeout)
            except SystemExit as e:
                print(f"[{s['name']}] FAILED {e}", flush=True)
                continue
            for f in out.glob("*.png"):
                f.rename(out / re.sub(r"_\d{5}_\.png$", "_00001_.png", f.name))
            print(f"[{s['name']}] {time.time() - t0:.0f} s -> {out}", flush=True)
    print("board ->", board(d, cfg["shots"]))


if __name__ == "__main__":
    main()
