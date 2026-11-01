"""Build studio preview proxies for existing projects (uploads and matte jobs make them for new ones).

  server/.venv/bin/python scripts/make_proxies.py --all
  server/.venv/bin/python scripts/make_proxies.py <project id> [...] [--force]

Writes media/proxy/<video stem>.mp4 + .full.mp4 and <matte dir>/fg_proxy.webm + fg_seek.webm next to the originals; project.json is untouched
(the studio finds proxies by convention). Skips files that already exist unless --force.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.config import settings  # noqa: E402
from app.media import encode_matte_proxy, encode_preview_proxy, proxy_rel, seek_rel  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    projects = settings.projects_dir
    ids = a.pids or ([d.name for d in sorted(projects.iterdir()) if (d / "project.json").exists()] if a.all else [])
    if not ids:
        ap.error("give project ids or --all")
    for pid in ids:
        pdir = projects / pid
        try:
            p = json.loads((pdir / "project.json").read_text())
        except Exception as e:
            print(f"{pid[:8]} skip: {e}")
            continue
        t0 = time.monotonic()
        made = []
        video = (p.get("media") or {}).get("video")
        if video and video.get("path"):
            src = pdir / video["path"]
            for out, full in ((pdir / proxy_rel(video["path"]), False), (pdir / seek_rel(video["path"]), True)):
                if src.exists() and (a.force or not out.exists()):
                    encode_preview_proxy(src, out, full=full)
                    made.append(f"{'video-full' if full else 'video'} {out.stat().st_size // 1024} KB")
        matte = (p.get("analysis") or {}).get("matte")
        if matte:
            mdir = pdir / matte.rstrip("/")
            for name, full in (("fg_proxy.webm", False), ("fg_seek.webm", True)):
                if mdir.is_dir() and (a.force or not (mdir / name).exists()):
                    out = encode_matte_proxy(mdir, float(p.get("fps") or 24), full=full)
                    if out:
                        made.append(f"{'matte-full' if full else 'matte'} {out.stat().st_size // 1024} KB")
        print(f"{pid[:8]} {p.get('name', '')[:40]:40s} {', '.join(made) or 'up to date'} ({time.monotonic() - t0:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
