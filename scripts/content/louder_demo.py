"""Fields demo project: one held word ("LOUDER") over a dance clip so the voice and motion fields read.

Copies a source project (media + analysis) to a new project whose only word is LOUDER, held from the first
sung "louder" to the end of the clip, behind the dancer, with look.fields set.
Usage: python scripts/content/louder_demo.py <source_project_id> [--name ...] [--start 2.7] [--motion 1 --voice 1]
"""
import argparse
import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ap = argparse.ArgumentParser()
ap.add_argument("source")
ap.add_argument("--name", default="LOUDER · fields demo")
ap.add_argument("--start", type=float, default=2.7)
ap.add_argument("--look", default="red-glow")
ap.add_argument("--motion", type=float, default=1.0)
ap.add_argument("--voice", type=float, default=1.0)
a = ap.parse_args()
src = ROOT / "data/projects" / a.source
pid = str(uuid.uuid4())
dst = ROOT / "data/projects" / pid
shutil.copytree(src, dst, ignore=shutil.ignore_patterns("export", "gen"))
p = json.loads((dst / "project.json").read_text())
p.update(id=pid, name=a.name, shots=[], lineMeta=None)
p["words"] = [{"id": "w_louder", "text": "LOUDER", "start": a.start, "end": round(p["duration"] - .05, 3), "lineId": "l_louder",
               "placement": "behind", "preset": "pop", "hero": True}]
p["look"] = {"id": a.look, "overrides": {"fields": {"motion": a.motion, "voice": a.voice}}}
(dst / "project.json").write_text(json.dumps(p, indent=2))
print(pid)
