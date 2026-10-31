"""Real local integration: API upload → deterministic browser capture → 3 video formats.
Run while the configured web URL and API :8787 are serving: server/.venv/bin/python server/tests/smoke_export.py
"""
import json
import subprocess
import time
from pathlib import Path
import httpx
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
fixture = ROOT / "server/tests/fixtures/smoke.mp4"
fixture.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x263a42:s=320x192:r=12:d=1", "-f", "lavfi", "-i", "sine=frequency=220:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(fixture)], check=True)
with httpx.Client(base_url="http://127.0.0.1:8787", timeout=60) as client:
    def checked(response):
        response.raise_for_status()
        return response.json()
    project = checked(client.post("/api/projects", json={"name": "Integration export"}))
    url = f"/api/projects/{project['id']}"
    with fixture.open("rb") as file:
        checked(client.post(url + "/media", data={"kind": "video"}, files={"file": (fixture.name, file, "video/mp4")}))
    project = checked(client.get(url))
    project["style"]["fontSize"] = .3
    # Left-half opaque foreground, right-half transparent: verifies real occlusion, not just codec tags.
    matte_dir = ROOT / "data/projects" / project["id"] / "analysis/test_matte"
    matte_dir.mkdir(parents=True)
    matte = Image.new("RGBA", (320, 192), (0, 0, 0, 0))
    ImageDraw.Draw(matte).rectangle((0, 0, 159, 191), fill=(0, 180, 0, 255))
    for i in range(1, 13):
        matte.save(matte_dir / f"fg_{i:05d}.png")
    subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-framerate", "12", "-i", str(matte_dir / "fg_%05d.png"), "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", str(matte_dir / "fg.webm")], check=True)
    project["analysis"]["matte"] = "analysis/test_matte/"
    project["words"] = [{"id": placement, "text": "HI", "start": 0, "end": 1, "lineId": placement, "placement": placement, "preset": "none", "position": {"x": .25, "y": y}} for placement, y in [("behind", .28), ("overlay", .73)]]
    checked(client.put(url, json=project))
    job = checked(client.post(url + "/export", json={"layer": "composite", "formats": ["mp4", "mov", "webm"]}))
    for _ in range(300):
        job = checked(client.get(f"/api/jobs/{job['id']}"))
        if job["status"] in ("done", "failed"):
            break
        time.sleep(1)
    print(json.dumps(job, indent=2))
    assert job["status"] == "done", job
    for kind, relative in job["result"]["files"].items():
        output = ROOT / "data/projects" / project["id"] / relative
        metadata = json.loads(subprocess.check_output(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)]))
        stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
        assert (stream["width"], stream["height"]) == (320, 192), stream
        if kind == "mov":
            assert stream["pix_fmt"].startswith("yuva"), stream
        if kind == "webm":
            assert stream.get("tags", {}).get("alpha_mode") == "1", stream
        print(kind, stream["codec_name"], stream["pix_fmt"])

    export_dir = ROOT / "data/projects" / project["id"] / "export" / job["id"]
    composite = Image.open(export_dir / "mp4_frames/frame_00006.png").convert("RGB")
    def whites(box):
        return sum(min(pixel) > 220 for pixel in composite.crop(box).getdata())
    assert whites((0, 0, 160, 96)) == 0, "Behind text leaked through opaque foreground"
    assert whites((0, 96, 160, 192)) > 50, "Overlay text was hidden by foreground"
    for kind, decode_args in [("webm", ["-c:v", "libvpx-vp9"]), ("mov", [])]:
        output = ROOT / "data/projects" / project["id"] / job["result"]["files"][kind]
        decoded = export_dir / f"alpha_{kind}.png"
        subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", *decode_args, "-i", str(output), "-frames:v", "1", str(decoded)], check=True)
        alpha = Image.open(decoded).convert("RGBA").getchannel("A")
        assert alpha.getextrema() == (0, 255), (kind, alpha.getextrema())
    print("PASS: behind/front occlusion and decoded alpha in both overlay formats")
    text_job = checked(client.post(url + "/export", json={"layer": "text", "formats": ["mp4"]}))
    for _ in range(120):
        text_job = checked(client.get(f"/api/jobs/{text_job['id']}"))
        if text_job["status"] in ("done", "failed"):
            break
        time.sleep(1)
    assert text_job["status"] == "done", text_job
    text_mp4 = ROOT / "data/projects" / project["id"] / text_job["result"]["files"]["mp4"]
    text_decoded = text_mp4.with_suffix(".png")
    subprocess.run(["/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-i", str(text_mp4), "-frames:v", "1", str(text_decoded)], check=True)
    text_pixels = Image.open(text_decoded).convert("RGB")
    assert max(text_pixels.getpixel((319, 0))) < 5, "Text-only MP4 must flatten on black"
    assert sum(min(p) > 220 for p in text_pixels.crop((0, 0, 160, 96)).getdata()) > 50
    print("PASS: layer=text MP4 is text on black, with behind words included")
