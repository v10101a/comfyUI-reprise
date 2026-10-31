"""Download remote ComfyUI outputs whose filename starts with a prefix (for jobs whose local poller was stopped).
  server/.venv/bin/python scripts/content/fetch_remote.py concept/s4_drop outputs/hero/plates/s4_drop"""
import sys, httpx
from pathlib import Path
base = "http://100.104.17.103:8188"; prefix, out = sys.argv[1], Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
h = httpx.get(f"{base}/history", params={"max_items": 60}, timeout=60).json()
for pid, e in h.items():
    for node in e.get("outputs", {}).values():
        for key in ("gifs", "videos", "images"):
            for f in node.get(key) or []:
                name = f"{f.get('subfolder','')}/{f['filename']}".lstrip("/")
                if name.startswith(prefix) and f.get("type") == "output":
                    data = httpx.get(f"{base}/view", params={"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": "output"}, timeout=600).content
                    (out / f["filename"]).write_bytes(data); print("saved", out / f["filename"])
