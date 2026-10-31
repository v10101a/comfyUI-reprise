"""Exercise real Comfy words/matte jobs through Typeset API using local synthetic fixtures."""
import json
import subprocess
import time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]
fixture = ROOT / "server/tests/fixtures/person_voice_short.mp4"
fixture.parent.mkdir(parents=True, exist_ok=True)
source = Path.home() / "ComfyUI/input/typeset/test/person_speech.mp4"
# Use full voice as a separate audio upload, and a one-second video for segmentation.
subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-i", str(source), "-t", "1", "-vf", "scale=512:320", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(fixture)], check=True)
with httpx.Client(base_url="http://127.0.0.1:8787", timeout=60) as client:
    def checked(response):
        response.raise_for_status()
        return response.json()
    project = checked(client.post("/api/projects", json={"name": "Comfy analysis integration"}))
    url = f"/api/projects/{project['id']}"
    for kind, path in [("video", fixture), ("audio", Path.home() / "ComfyUI/input/typeset/test/speech.wav")]:
        with path.open("rb") as file:
            checked(client.post(url + "/media", data={"kind": kind}, files={"file": (path.name, file)}))
    for action in ["words", "matte"]:
        job = checked(client.post(url + f"/analyze/{action}", json={}))
        for _ in range(900):
            job = checked(client.get(f"/api/jobs/{job['id']}"))
            if job["status"] in ("done", "failed"):
                break
            time.sleep(1)
        print(json.dumps(job, indent=2), flush=True)
        assert job["status"] == "done", job
    project = checked(client.get(url))
    assert len(project["words"]) > 2, project
    assert all(0 <= w["start"] < w["end"] <= project["duration"] for w in project["words"]), project
    assert project["analysis"]["matte"] and project["analysis"]["tracks"], project
    pdir = ROOT / "data/projects" / project["id"]
    tracks = json.loads((pdir / project["analysis"]["tracks"]).read_text())
    assert tracks["frames"] >= 24, tracks
    assert len(list((pdir / project["analysis"]["matte"]).glob("fg_*.png"))) >= 24
    print("PASS", project["id"], len(project["words"]), "words", tracks["frames"], "tracked frames", flush=True)
