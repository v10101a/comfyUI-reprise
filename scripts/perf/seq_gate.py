"""Gate for #/render?decode=seq: capture every frame with the default seek path and with sequential decode, compare
PNG bytes frame by frame, report timing. Read-only on projects (renders from the live project.json).

  nice -n 10 server/.venv/bin/python scripts/perf/seq_gate.py <pid> [<pid> ...] [--out outputs/perf/seq_gate]
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from app.capture import capture  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pids", nargs="+")
    ap.add_argument("--web", default="http://127.0.0.1:5174")
    ap.add_argument("--server", default="http://127.0.0.1:8787")
    ap.add_argument("--out", default=str(ROOT / "outputs/perf/seq_gate"))
    ap.add_argument("--frames", type=int, default=0, help="limit (0 = all)")
    a = ap.parse_args()
    report = []
    for pid in a.pids:
        p = json.load(urllib.request.urlopen(f"{a.server}/api/projects/{pid}"))
        n = a.frames or max(1, int(p["duration"] * p["fps"] + .5))
        base = f"{a.web}/#/render?project={quote(pid)}&layer=composite&server={quote(a.server, safe='')}"
        row = {"project": pid, "name": p["name"], "size": f"{p['width']}x{p['height']}", "frames": n}
        dirs = {}
        for mode, url in (("seek", base + "&decode=seek"), ("seq", base + "&decode=seq")):
            d = Path(a.out) / pid[:8] / mode
            d.mkdir(parents=True, exist_ok=True)
            for f in d.glob("frame_*.png"):
                f.unlink()
            t0 = time.monotonic()
            capture(url, p["width"], p["height"], n, d, timeout=120)
            row[f"{mode}_s"] = round(time.monotonic() - t0, 1)
            row[f"{mode}_fps"] = round(n / (time.monotonic() - t0), 2)
            dirs[mode] = d
            print(json.dumps({"project": pid[:8], "mode": mode, "seconds": row[f"{mode}_s"], "fps": row[f"{mode}_fps"]}), flush=True)
        bad = [i for i in range(n) if (dirs["seek"] / f"frame_{i:05d}.png").read_bytes() != (dirs["seq"] / f"frame_{i:05d}.png").read_bytes()]
        row["mismatched"] = len(bad)
        row["first_mismatches"] = bad[:10]
        row["identical"] = not bad
        report.append(row)
        print(json.dumps(row), flush=True)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
