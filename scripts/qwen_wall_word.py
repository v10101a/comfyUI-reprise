"""Write a word into a real frame as a physical object with local Qwen-Image-Edit-2511 (int8, 4-step Lightning).

  ~/ComfyUI/.venv/bin/python scripts/qwen_wall_word.py --frame outputs/concept-tests/walk_night/frame_072.png \
      --text "HOLD ON" --prompt "painted in large white block letters on the brick wall behind the woman, slightly weathered" \
      --out outputs/concept-tests/proofs/wall_holdon [--width 768 --height 448] [--seed 7]

Runs through ComfyUI's raw HTTP API on :8188 (local). ~4–5 minutes at 768×448 on the M5 Max; larger sizes scale roughly with pixels.
"""
import argparse
import json
import shutil
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMFY = "http://127.0.0.1:8188"
COMFY_INPUT = Path.home() / "ComfyUI/input/typeset/concept"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True, type=Path)
    ap.add_argument("--text", required=True)
    ap.add_argument("--prompt", required=True, help="how/where the word appears; the script prepends the exact-word instruction")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=448)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    COMFY_INPUT.mkdir(parents=True, exist_ok=True)
    staged = COMFY_INPUT / f"{a.frame.stem}_{uuid.uuid4().hex[:6]}{a.frame.suffix}"
    shutil.copy(a.frame, staged)
    g = json.loads((ROOT / "workflows/eval/qwen2511_int8_edit.api.json").read_text())
    g["4"]["inputs"]["image"] = f"typeset/concept/{staged.name}"
    g["5"]["inputs"].update({"width": a.width, "height": a.height})
    g["6"]["inputs"]["prompt"] = (f"Add the exact text \"{a.text}\" {a.prompt}. Spell it exactly \"{a.text}\". "
                                  "Keep the person, camera framing, lighting and everything else unchanged.")
    g["11"]["inputs"]["seed"] = a.seed
    g["13"]["inputs"]["filename_prefix"] = f"typeset/concept/{a.out.name}"

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "workflow.json").write_text(json.dumps(g, indent=2))
    pid = str(uuid.uuid4())
    req = urllib.request.Request(f"{COMFY}/prompt", data=json.dumps({"prompt": g, "prompt_id": pid, "client_id": pid}).encode(),
                                 headers={"content-type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req).read())
    if "error" in resp:
        raise SystemExit(json.dumps(resp, indent=2)[:2000])
    t0 = time.time()
    print("submitted", pid)
    while True:
        h = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}").read())
        if pid in h:
            break
        time.sleep(5)
    entry = h[pid]
    status = entry.get("status", {}).get("status_str")
    print(f"{status} in {time.time() - t0:.0f}s")
    if status != "success":
        raise SystemExit(json.dumps(entry.get("status"), indent=2)[:3000])
    for node in entry["outputs"].values():
        for img in node.get("images", []):
            params = f"filename={img['filename']}&subfolder={img.get('subfolder', '')}&type={img['type']}"
            data = urllib.request.urlopen(f"{COMFY}/view?{params}").read()
            dest = a.out / img["filename"]
            dest.write_bytes(data)
            print("saved", dest)


if __name__ == "__main__":
    main()
