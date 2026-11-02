"""Offline API and storage regression tests; no ComfyUI or browser required."""
import os
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.TemporaryDirectory()
os.environ["TYPESET_DATA_DIR"] = TMP.name
os.environ.setdefault("TYPESET_ANALYSIS_ENGINE", "local")  # offline: in-process path, never a live ComfyUI

from fastapi.testclient import TestClient
from app.main import app, store
from app.media import make_test_video
from app.models import Project
from app.pipeline import project_path, timeline_words


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.video = make_test_video(Path(TMP.name) / "source.mp4", duration=.5, fps=24, size="160x96")

    def create(self):
        response = self.client.post("/api/projects", json={"name": "Test"})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_project_roundtrip_and_invalid_timing(self):
        project = self.create()
        project["duration"] = 1
        project["words"] = [{"id": "w", "lineId": "l", "text": "Hello", "start": .1, "end": .8, "placement": "behind", "preset": "pop"}]
        saved = self.client.put(f"/api/projects/{project['id']}", json=project)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{project['id']}").json()["words"][0]["placement"], "behind")
        project["words"][0]["end"] = .05
        self.assertEqual(self.client.put(f"/api/projects/{project['id']}", json=project).status_code, 422)

    def test_hud_pointer_settings_roundtrip(self):
        p = store.create('HUD pointer')
        pointer = {'point': {'u': .72, 'v': -.1}, 'dot': False, 'connector': True,
                   'dotColor': '#ff000080', 'connectorColor': '#0000ff'}
        body = p.model_dump(mode='json')
        body['lineMeta'] = {'line': {'hud': pointer, 'fill': '#ffffff'}}
        response = self.client.put(f'/api/projects/{p.id}', json=body)
        self.assertEqual(response.status_code, 200, response.text)
        saved = self.client.get(f'/api/projects/{p.id}').json()
        self.assertEqual(saved['lineMeta']['line']['hud'], pointer)
        self.assertEqual(saved['lineMeta']['line']['fill'], '#ffffff')

    def test_stale_save_preserves_completed_analysis_for_same_video(self):
        from app.models import MediaRef
        p = store.create("stale editor")
        p.media.video = MediaRef(path="media/original.mp4", duration=1)
        store.save(p)
        stale = p.model_copy(deep=True)
        p.analysis.matte, p.analysis.tracks = "analysis/matte/", "analysis/tracks.json"
        p.analysis.headTracks = {"media/clip.mp4": "analysis/heads_clip.json"}
        store.save(p)
        stale.name = "new lyrics edit"
        r = self.client.put(f"/api/projects/{p.id}", json=stale.model_dump(mode="json"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["analysis"]["matte"], "analysis/matte/")
        self.assertEqual(r.json()["analysis"]["headTracks"], p.analysis.headTracks)
        self.assertEqual(r.json()["name"], "new lyrics edit")
        stale.media.video.path = "media/replacement.mp4"
        r = self.client.put(f"/api/projects/{p.id}", json=stale.model_dump(mode="json"))
        self.assertIsNone(r.json()["analysis"]["matte"])

    def test_generation_direction_roundtrips_and_request_reaches_runner(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from app.models import InworldBody, MediaRef, Word
        from app.pipeline import generate_inworld
        p = store.create("shot direction")
        p.duration = 5
        p.media.video = MediaRef(path="media/source.mp4", duration=5)
        p.words = [Word(id="w", lineId="line", text="Stay!", start=1, end=3)]
        p.lineMeta = {"line": {"scale": 1.4, "generation": {"lettering": "Copper on concrete", "camera": "locked", "seed": 0}}}
        saved = self.client.put(f"/api/projects/{p.id}", json=p.model_dump(mode="json"))
        self.assertEqual(saved.json()["lineMeta"], p.lineMeta)
        body = InworldBody(wordIds=["w"], start=1, end=3, engine="remote-minimax", prompt="Copper on concrete",
                           motionPrompt="Static shot. Lips closed.", longEdge=1344, seed=0)
        result = {"timings": {"video": 1}, "size": [1344, 768], "length": 48}
        with patch("app.remote_gen.run_remote_shot", return_value=result) as run:
            generate_inworld(store, p.id, body, SimpleNamespace(progress=lambda *a: None))
        self.assertEqual(run.call_args.kwargs["seed"], 0)
        self.assertEqual(run.call_args.kwargs["motion"], body.motionPrompt)
        self.assertEqual(run.call_args.kwargs["long_edge"], 1344)
        final = store.load(p.id)
        self.assertEqual(final.shots[-1].request, body.model_dump(mode="json"))
        self.assertEqual(final.words[0].placement, "inworld")

    def test_export_snapshot_allows_concurrent_save(self):
        import json
        import threading
        from types import SimpleNamespace
        from urllib.parse import parse_qs, urlparse
        from unittest.mock import patch
        from app.exporter import export_project
        from app.models import ExportBody
        p = store.create("before edit")
        p.duration = 1
        store.save(p)
        saved = threading.Event()
        workers = []
        def capture(url, width, height, frames, dest, *args):
            source = parse_qs(urlparse(url).fragment.split("?", 1)[1])["src"][0]
            self.assertTrue(source.endswith("/export/snapshot-test/project.json"))
            def edit():
                store.update(p.id, lambda q: setattr(q, "name", "edited during render"))
                saved.set()
            t = threading.Thread(target=edit);workers.append(t);t.start()
            self.assertTrue(saved.wait(1), "Export blocked the save lock")
            snapshot = json.loads((store.project_dir(p.id)/"export/snapshot-test/project.json").read_text())
            self.assertEqual(snapshot["name"], "before edit")
            return dest/"frame_%05d.png"
        try:
            with patch("app.exporter.capture", side_effect=capture), patch("app.exporter.ffmpeg"):
                export_project(store, p.id, ExportBody(formats=["mp4"]), SimpleNamespace(id="snapshot-test", progress=lambda *a: None))
        finally:
            for t in workers:t.join(2)
        self.assertEqual(store.load(p.id).name, "edited during render")

    def test_upload_probe_and_path_validation(self):
        project = self.create()
        url = f"/api/projects/{project['id']}"
        with self.video.open("rb") as file:
            response = self.client.post(url + "/media", data={"kind": "video"}, files={"file": ("../../source.mp4", file, "video/mp4")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["width"], 160)
        project = self.client.get(url).json()
        self.assertEqual(project["width"], 160)
        self.assertTrue(project["media"]["video"]["hasAudio"])
        self.assertEqual(self.client.get(f"/files/projects/{project['id']}/{response.json()['path']}").status_code, 200)
        project["media"]["video"]["path"] = "../../outside.mp4"
        self.assertEqual(self.client.put(url, json=project).status_code, 400)
        with self.assertRaises(ValueError):
            store.project_dir("../escape")
        with self.assertRaises(ValueError):
            project_path(store, project["id"], "/etc/passwd")

    def test_reference_upload_keeps_media(self):
        import io
        from PIL import Image
        project = self.create()
        url = f"/api/projects/{project['id']}"
        buf = io.BytesIO()
        Image.new("RGB", (64, 96), (200, 40, 160)).save(buf, "PNG")
        r = self.client.post(url + "/media", data={"kind": "reference"}, files={"file": ("ref.png", buf.getvalue(), "image/png")})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["width"], r.json()["height"]), (64, 96))
        self.assertTrue(r.json()["path"].startswith("media/"))
        self.assertIsNone(self.client.get(url).json()["media"]["video"])
        bad = self.client.post(url + "/media", data={"kind": "reference"}, files={"file": ("x.png", b"not an image", "image/png")})
        self.assertEqual(bad.status_code, 400)

    def test_long_audio_is_clipped_to_video_timeline(self):
        raw = {"words": [
            {"text": "inside", "start": .1, "end": .4},
            {"text": "crossing", "start": .8, "end": 1.2},
            {"text": "outside", "start": 1.2, "end": 1.5},
        ]}
        words = timeline_words(raw, 1.)
        self.assertEqual([w.text for w in words], ["inside", "crossing"])
        self.assertEqual(words[-1].end, 1.)
        self.assertEqual(raw["words"][-1]["end"], 1.5)  # full analysis remains intact

    def test_preconditions_and_identity(self):
        project = self.create()
        url = f"/api/projects/{project['id']}"
        self.assertEqual(self.client.post(url + "/analyze/words", json={}).status_code, 400)
        self.assertEqual(self.client.post(url + "/analyze/matte", json={}).status_code, 400)
        self.assertEqual(self.client.post(url + "/export", json={"formats": ["mp4"]}).status_code, 400)
        project["id"] = "different"
        self.assertEqual(self.client.put(url, json=project).status_code, 400)
        self.assertEqual(self.client.get("/api/jobs/missing").status_code, 404)

    def wait(self, job):
        import time
        for _ in range(200):
            j = self.client.get(f"/api/jobs/{job['id']}").json()
            if j["status"] in ("done", "failed"):
                return j
            time.sleep(.05)
        self.fail("job did not finish")

    def test_v2_surface_track_and_reframe(self):
        project = self.create()
        url = f"/api/projects/{project['id']}"
        self.assertEqual(self.client.post(url + "/analyze/occupancy").status_code, 400)  # no matte yet
        with self.video.open("rb") as file:
            self.assertEqual(self.client.post(url + "/media", data={"kind": "video"}, files={"file": ("v.mp4", file, "video/mp4")}).status_code, 200)
        self.assertEqual(self.client.post(url + "/surfaces/nope/track").status_code, 404)
        project = self.client.get(url).json()
        project["surfaces"] = [{"id": "s1", "keyFrame": 3, "corners": [[.2, .2], [.8, .2], [.8, .8], [.2, .8]]}]
        project["words"] = [{"id": "w", "lineId": "l", "text": "Wall", "start": 0, "end": .4, "placement": "surface", "surfaceId": "s1"},
                            {"id": "v", "lineId": "m", "text": "A very long caption line indeed", "start": 0, "end": .4,
                             "placement": "overlay", "position": {"x": .5, "y": .8}}]
        self.assertEqual(self.client.put(url, json=project).status_code, 200)
        job = self.wait(self.client.post(url + "/surfaces/s1/track").json())
        self.assertEqual(job["status"], "done", job["message"])
        saved = self.client.get(url).json()
        self.assertEqual(saved["surfaces"][0]["status"], "tracked")
        self.assertEqual(saved["words"][0]["surfaceId"], "s1")
        track = self.client.get(f"/files/projects/{project['id']}/{saved['surfaces'][0]['track']}").json()
        self.assertTrue(any(fr["f"] == 3 for fr in track["frames"]))
        job = self.wait(self.client.post(url + "/reframe", json={"aspect": "9:16"}).json())
        self.assertEqual(job["status"], "done", job["message"])
        new = self.client.get(f"/api/projects/{job['result']['projectId']}").json()
        self.assertEqual(new["frame"]["aspect"], "9:16")
        self.assertLess(new["width"], new["height"])
        crop = self.client.get(f"/files/projects/{new['id']}/analysis/crop.json").json()
        self.assertEqual(len(crop["frames"]), 12)
        self.assertTrue(all(0 <= f["x"] and f["x"] + f["w"] <= 1.0001 for f in crop["frames"]))
        caption = next(w for w in new["words"] if w["id"] == "v")
        self.assertIsNone(caption["position"])
        self.assertTrue(caption["autoPlace"])
        self.assertLess(caption["style"]["fontSize"], 0.08)
        self.assertFalse(new["lineMeta"]["m"]["subtitle"])
        self.assertEqual(self.client.get(f"/files/projects/{new['id']}/{new['media']['video']['path']}").status_code, 200)

    def test_assets_are_additive_and_add_layers(self):
        import io, json
        from PIL import Image
        from app.config import settings
        pid = self.create()["id"]
        with self.video.open("rb") as fh:
            self.client.post(f"/api/projects/{pid}/media", data={"kind": "video"}, files={"file": ("plate.mp4", fh, "video/mp4")})
        plate = self.client.get(f"/api/projects/{pid}").json()["media"]["video"]
        with self.video.open("rb") as fh:
            sky = self.client.post(f"/api/projects/{pid}/assets", data={"addLayer": "true"}, files={"file": ("sky.mp4", fh, "video/mp4")}).json()
        self.assertEqual((sky["kind"], sky["source"]["kind"], sky["layer"]["assetId"]), ("video", "upload", sky["id"]))
        png = io.BytesIO(); Image.new("RGB", (32, 16), "red").save(png, "PNG")
        tex = self.client.post(f"/api/projects/{pid}/assets", data={"addLayer": "top"}, files={"file": ("tex.png", png.getvalue(), "image/png")}).json()
        self.assertEqual((tex["kind"], tex["width"], tex["height"]), ("image", 32, 16))
        p = self.client.get(f"/api/projects/{pid}").json()
        self.assertEqual(p["media"]["video"], plate)  # the plate is untouched
        stale = dict(p); stale.pop("assets"); stale.pop("layers")  # an editor opened before the imports saves
        self.assertEqual(self.client.put(f"/api/projects/{pid}", json=stale).status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{pid}").json()["layers"], p["layers"])
        self.assertEqual([a["id"] for a in p["assets"]], [sky["id"], tex["id"]])
        self.assertEqual([l.get("assetId") or l["kind"] + l.get("which", "") for l in p["layers"]],
                         ["plate", sky["id"], "textbehind", "subject", "textfront", tex["id"]])
        out = settings.comfy_dir / "output"
        if out.is_dir():  # Comfy output ref (only where a ComfyUI install exists)
            name = f"typeset_test_{pid[:8]}.png"; (out / name).write_bytes(png.getvalue())
            try:
                got = self.client.post(f"/api/projects/{pid}/assets", json={"comfy": {"filename": name, "subfolder": "", "type": "output"},
                                       "source": {"kind": "workflow", "workflowId": "wf"}})
                self.assertEqual(got.status_code, 200, got.text)
                self.assertEqual((got.json()["source"]["kind"], got.json()["source"]["filename"]), ("workflow", name))
            finally:
                (out / name).unlink(missing_ok=True)
        self.assertEqual(self.client.post(f"/api/projects/{pid}/assets", json={"comfy": {"filename": "../../etc/passwd"}}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
