"""MiniMax H3 reference-to-video on the remote 4090: keeps one character's identity across shots.

  server/.venv/bin/python scripts/content/minimax_ref.py --jobs scripts/content/hero_ref_shots.json --out outputs/hero/plates

Each job: {name, prompt (use <Picture 1> for the reference), seed, ref (local png), first_frame? (local png, optional i2v start)}.
Reuses build/upload/run helpers from scripts/remote_minimax.py.
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from remote_minimax import BASE_GRAPH, upload_image, run  # noqa: E402

def build(prompt, seed, ref_remote, prefix, width=1344, height=768, length=124, ref_size="match", first_remote=None):
    g = json.loads(BASE_GRAPH.read_text())
    g["5"]["inputs"]["image"] = ref_remote
    g["6"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
        "clip": ["3", 0], "vae": ["4", 0], "audio_vae": ["13", 0], "prompt": prompt, "width": width, "height": height,
        "length": length, "ref_image_size": ref_size, "ref_images.ref_image_1": ["5", 0]}}
    if first_remote:
        # add the first frame as a guide at frame 0 on top of the reference conditioning
        g["16"] = {"class_type": "LoadImage", "inputs": {"image": first_remote}}
        g["17"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {"positive": ["6", 0], "latent": ["6", 1], "frame_idx": 0, "vae": ["4", 0], "image": ["16", 0]}}
        g["8"]["inputs"]["conditioning"] = ["17", 0]
        # MiniMaxH3AddGuide outputs only CONDITIONING; the sampler keeps node 6's latent.
    g["7"]["inputs"]["noise_seed"] = seed
    g["15"]["inputs"]["filename_prefix"] = prefix
    return g

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://100.104.17.103:8188")
    p.add_argument("--jobs", type=Path, required=True)
    p.add_argument("--only", nargs="*")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    for j in json.loads(a.jobs.read_text()):
        if a.only and j["name"] not in a.only:
            continue
        ref = upload_image(a.base, Path(j["ref"]), "typeset/hero")
        first = upload_image(a.base, Path(j["first_frame"]), "typeset/hero") if j.get("first_frame") else None
        g = build(j["prompt"], j.get("seed", 7), ref, f"hero/{j['name']}", length=j.get("length", 124),
                  ref_size=j.get("ref_size", "match"), first_remote=first)
        try:
            run(a.base, g, a.out / j["name"], 1800)
        except SystemExit as e:
            print(f"[{j['name']}] FAILED: {e}", flush=True)

if __name__ == "__main__":
    main()
