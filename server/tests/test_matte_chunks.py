"""Offline: the matte job splits long clips into bounded chunks and merges them exactly (fake runner)."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TMP = tempfile.TemporaryDirectory()
os.environ.setdefault("TYPESET_DATA_DIR", TMP.name)
os.environ.setdefault("TYPESET_ANALYSIS_ENGINE", "local")

import numpy as np
from PIL import Image

from app import pipeline, vision
from app.comfy import RunResult
from app.main import store
from app.media import make_test_video


class Ctx:
    id = "job12345"
    def __init__(self): self.messages = []
    def progress(self, frac, msg=None): self.messages.append((frac, msg))


def box(f):
    return 5 + f % 30  # subject x position at frame f


def raw_frame(f):
    x = box(f)
    return {"f": f, "bbox": [round(x / 80, 4), round(10 / 48, 4), round(20 / 80, 4), round(35 / 48, 4)],
            "cx": x / 80 + 10 / 80, "cy": 10 / 48 + 35 / 48 * 0.1}


def fake_run_factory(calls):
    """Pretend BiRefNet + MaskToTracks(raw, frame_offset): PNGs of a drifting box and raw track frames."""
    def run(name, inputs, out_dir, progress=None):
        from app.pipeline import count_frames
        calls.append(dict(inputs))
        n = count_frames(Path(inputs["_local"]))
        out_dir.mkdir(parents=True, exist_ok=True)
        pngs, frames = [], []
        for i in range(n):
            f = inputs["frame_offset"] + i
            rgba = np.zeros((48, 80, 4), np.uint8); rgba[10:45, box(f):box(f) + 20, 3] = 255
            q = out_dir / f"fg_{i:05d}_.png"; Image.fromarray(rgba).save(q); pngs.append(q)
            frames.append(raw_frame(f))
        if not inputs["raw_tracks"]:
            frames = vision.smooth_track_frames(frames, 3)
        tj = out_dir / "tracks.json"
        tj.write_text(json.dumps({"fps": inputs["fps"], "frames": n, "tracks": [{"id": "person0", "label": "person", "frames": frames}]}))
        return RunResult(name=name, job_id="x", status="success", outputs={"fg_png": pngs, "tracks_json": [tj]}, timing={})
    return run


def make_project(name):
    p = store.create(name)
    video = make_test_video(Path(TMP.name) / f"{name}.mp4", duration=2.0, fps=24, size="80x48")
    rel = "media/clip.mp4"
    (store.project_dir(p.id) / "media").mkdir(parents=True, exist_ok=True)
    os.link(video, store.project_dir(p.id) / rel)
    from app.media import probe_media
    ref = probe_media(store.project_dir(p.id) / rel, rel)
    def setup(pr):
        pr.media.video = ref; pr.width, pr.height, pr.fps, pr.duration = 80, 48, 24.0, 2.0
    store.update(p.id, setup)
    return p


class MatteChunkTests(unittest.TestCase):
    def setUp(self):
        self.comfy_in = Path(tempfile.mkdtemp(dir=TMP.name))
        self.staged = {}
        self.calls = []
        self.run = fake_run_factory(self.calls)

    def stage(self, src, pid, *parts):
        key = "/".join(("typeset", pid) + parts)
        dest = self.comfy_in / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.link(src, dest)
        self.staged[key] = src
        return key

    def patches(self, run):
        from types import SimpleNamespace
        return [mock.patch.object(pipeline, "runner", mock.Mock(run=run, comfyui_url="http://comfy.invalid")),
                mock.patch.object(pipeline, "stage_to_comfy_input", self.stage),
                mock.patch.object(pipeline, "settings", SimpleNamespace(comfy_input_dir=self.comfy_in)),
                mock.patch.object(pipeline, "matte_chunk_frames", lambda w, h: 10),
                mock.patch.object(pipeline, "encode_alpha_webm", lambda *a, **k: None)]

    def run_matte(self, pid, run):
        import contextlib
        with contextlib.ExitStack() as st:
            for pt in self.patches(run):
                st.enter_context(pt)
            free = st.enter_context(mock.patch.object(pipeline, "free_comfy_models"))
            try:
                return pipeline.analyze_matte(store, pid, Ctx()), free
            except Exception as exc:
                return exc, free

    def test_mid_loop_failure_cleans_up_and_unloads(self):
        p = make_project("chunks_fail")
        def run_local(name, inputs, out_dir, progress=None):
            if len(self.calls) == 2:  # third chunk fails inside ComfyUI
                self.calls.append(dict(inputs))
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "partial.png").write_bytes(b"x")
                raise RuntimeError("ComfyUI crashed")
            return self.run(name, dict(inputs, _local=str(self.staged[inputs["video"]])), out_dir, progress)
        exc, free = self.run_matte(p.id, run_local)
        self.assertIsInstance(exc, RuntimeError)
        self.assertEqual(len(self.calls), 3)
        free.assert_called_once()
        work = store.project_dir(p.id) / "analysis" / Ctx.id
        self.assertFalse((work / "chunks").exists())
        self.assertFalse(list(work.glob("run_*")))
        self.assertFalse((self.comfy_in / "typeset" / p.id / Ctx.id).exists())
        self.assertIsNone(store.load(p.id).analysis.tracks)  # nothing half-written into the project

    def test_long_clip_is_chunked_and_matches_single_pass(self):
        p = make_project("chunks")
        def run_local(name, inputs, out_dir, progress=None):
            return self.run(name, dict(inputs, _local=str(self.staged[inputs["video"]])), out_dir, progress)
        out, free = self.run_matte(p.id, run_local)
        calls = self.calls
        free.assert_not_called()
        self.assertFalse((self.comfy_in / "typeset" / p.id / Ctx.id).exists())
        self.assertEqual(out["frames"], 48)
        self.assertEqual(out["chunks"], 5)
        self.assertEqual([c["frame_offset"] for c in calls], [0, 10, 20, 30, 40])
        self.assertEqual([c["unload_model"] for c in calls], [False] * 4 + [True])
        self.assertTrue(all(c["raw_tracks"] for c in calls))
        pdir = store.project_dir(p.id)
        mattes = sorted((pdir / out["matte"]).glob("fg_*.png"))
        self.assertEqual(len(mattes), 48)
        self.assertEqual(mattes[0].name, "fg_00001.png")
        # Single pass over the same frames: one smoothing over the whole clip.
        whole = {"fps": 24.0, "frames": 48, "tracks": [{"id": "person0", "label": "person",
                 "frames": vision.smooth_track_frames([raw_frame(f) for f in range(48)], 3)}]}
        got = json.loads((pdir / out["tracks"]).read_text())
        self.assertEqual(json.dumps(got, sort_keys=True), json.dumps(whole, sort_keys=True))
        self.assertFalse(list((pdir / "analysis" / "job12345").glob("run_*")))  # chunk runs cleaned up
        occ = json.loads((pdir / out["occupancy"]).read_text())
        self.assertEqual(len(occ["frames"]), 48)

    def test_free_posts_unload_and_never_raises(self):
        with mock.patch.object(pipeline, "runner", mock.Mock(comfyui_url="http://comfy.invalid")), \
             mock.patch("httpx.post") as post:
            pipeline.free_comfy_models()
        post.assert_called_once_with("http://comfy.invalid/free", json={"unload_models": True, "free_memory": True}, timeout=10)
        with mock.patch.object(pipeline, "runner", mock.Mock(comfyui_url="http://comfy.invalid")), \
             mock.patch("httpx.post", side_effect=OSError("down")):
            pipeline.free_comfy_models()  # swallowed

    def test_chunk_size_is_bounded(self):
        self.assertEqual(pipeline.matte_chunk_frames(1080, 1280), 46)
        self.assertEqual(pipeline.matte_chunk_frames(3840, 2160), 8)
        self.assertEqual(pipeline.matte_chunk_frames(160, 96), 240)


if __name__ == "__main__":
    unittest.main()
