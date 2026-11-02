"""Run a list of Wan S2V singing-take jobs sequentially on the 4090 (scripts/remote_s2v.py per job).

  ~/dev/lipsync/.venv/bin/python scripts/s2v_jobs.py outputs/songs/jobs/jobs_real.json [--only name1,name2] [--force]

Job keys: name, image, audio, mux_audio, start, dur, prompt, seed?, width?, height?, steps?, pre?, face_y?, crop?
Jobs whose <name>_mux.mp4 already exists are skipped unless --force. Uses this interpreter (needs httpx, PIL,
OpenCV 4 with CascadeClassifier for the face-centred crop; the server venv's OpenCV 5 lacks it).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from song_paths import singing_output_root

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("jobs", type=Path)
    p.add_argument("--only", help="comma-separated job names")
    p.add_argument("--force", action="store_true")
    p.add_argument("--out", type=Path, help="override each song's singing/ output directory")
    a = p.parse_args()
    jobs = json.loads(a.jobs.read_text())
    only = set(a.only.split(",")) if a.only else None
    failed = []
    for j in jobs:
        name = j["name"]
        if only and name not in only:
            continue
        out = a.out or singing_output_root(name, j.get('audio', ''))
        if not a.force and (out / name / f"{name}_mux.mp4").is_file():
            print(f"== {name}: done already", flush=True)
            continue
        cmd = [sys.executable, str(ROOT / "scripts/remote_s2v.py"), "--name", name, "--image", j["image"], "--audio", j["audio"],
               "--start", str(j["start"]), "--dur", str(j["dur"]), "--prompt", j["prompt"], "--out", str(out)]
        if j.get("mux_audio"):
            cmd += ["--mux-audio", j["mux_audio"]]
        for k in ("seed", "width", "height", "steps", "pre", "face_y", "cfg", "shift", "stretch", "mux_start", "motion", "motion_seconds"):
            if k in j:
                cmd += [f"--{k.replace('_', '-')}", str(j[k])]
        if j.get("crop"):
            cmd += ["--crop", *map(str, j["crop"])]
        if j.get("no_face_crop"):
            cmd.append("--no-face-crop")
        print(f"== {name}", flush=True)
        r = subprocess.run(cmd, cwd=ROOT)
        print(f"exit {r.returncode}", flush=True)
        if r.returncode:
            failed.append(name)
    print("jobs done" + (f" (failed: {', '.join(failed)})" if failed else ""), flush=True)


if __name__ == "__main__":
    main()
