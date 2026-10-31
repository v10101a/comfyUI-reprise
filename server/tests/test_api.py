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
        self.assertEqual(self.client.get(f"/files/projects/{new['id']}/{new['media']['video']['path']}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
