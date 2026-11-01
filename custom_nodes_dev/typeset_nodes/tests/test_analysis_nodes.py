"""Pure-function and node-level tests for the analysis nodes (CPU, no ComfyUI server needed)."""
import importlib
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
import os
sys.path.insert(0, os.environ.get("COMFYUI_DIR", str(Path.home() / "ComfyUI")))  # folder_paths for the pack __init__
pack = importlib.import_module("typeset_nodes.analysis_nodes")
cv = importlib.import_module("typeset_nodes.core_vision")
beats = importlib.import_module("typeset_nodes.beats")


def textured(h, w, seed=0):
    import cv2
    rng = np.random.default_rng(seed)
    t = cv2.resize(rng.integers(0, 255, (h // 8, w // 8), dtype=np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
    return cv2.GaussianBlur(t, (3, 3), 0)


class AnalysisNodeTests(unittest.TestCase):
    def test_occupancy_node_matches_core(self):
        mask = torch.zeros(3, 90, 160)
        mask[:, :, :80] = 1.0
        raw, prev = pack.TypesetOccupancyGrid().run(mask, 24.0, 32, preview_frames=2)
        doc = json.loads(raw)
        self.assertEqual((doc["cols"], doc["rows"], len(doc["frames"])), (32, 18, 3))
        cells = cv.decode_occupancy(doc["frames"][0], 32, 18)
        self.assertTrue((cells[:, :16] == 255).all() and (cells[:, 16:] == 0).all())
        self.assertEqual(prev.shape[0], 2)
        self.assertEqual(prev.shape[-1], 3)

    def test_planar_track_node_follows_pan(self):
        W, H, N = 240, 160, 12
        plane = textured(300, 600)
        frames = np.stack([np.repeat(plane[50:50 + H, 100 + 4 * t:100 + 4 * t + W, None], 3, -1) for t in range(N)])
        images = torch.from_numpy(frames.astype(np.float32) / 255)
        corners = [[0.3, 0.3], [0.6, 0.3], [0.6, 0.7], [0.3, 0.7]]
        raw, prev, n = pack.TypesetPlanarTrack().run(images, json.dumps(corners), 6, 24.0, smooth=0, preview_frames=3)
        doc = json.loads(raw)
        self.assertEqual(n, N)
        last = next(fr for fr in doc["frames"] if fr["f"] == N - 1)
        # content moves left by 4 px per frame → quad moves left by 4*(N-1-6) px
        self.assertAlmostEqual(last["corners"][0][0] * W, 0.3 * W - 4 * (N - 1 - 6), delta=1.0)
        self.assertEqual(prev.shape[0], 3)

    def test_planar_track_low_texture_wall_stays_rigid(self):
        """Near-blank wall (soft light falloff + a few faint marks) panning under a moving occluder: the quad must
        translate, not skew/shrink, and confidence must come from alignment."""
        import cv2
        W, H, N, key = 320, 180, 40, 20
        yy, xx = np.mgrid[0:H + 40, 0:W + 200].astype(np.float32)
        wall = 150 + 40 * np.exp(-((xx - 200) ** 2) / (2 * 60 ** 2)) + np.random.default_rng(1).normal(0, 1.5, xx.shape)
        for x, y in [(40, 50), (120, 140), (210, 30), (300, 120), (380, 80), (470, 150)]:
            cv2.circle(wall, (x, y), 3, 110, -1)
        wall = cv2.GaussianBlur(wall, (0, 0), 1.2).clip(0, 255).astype(np.uint8)
        frames, alphas = [], []
        for t in range(N):
            fr = wall[20:20 + H, 3 * t:3 * t + W].copy()
            a = np.zeros((H, W), np.uint8)
            cv2.rectangle(a, (30 + 6 * t, 20), (70 + 6 * t, H), 255, -1)
            frames.append(np.where(a > 0, 30, fr).astype(np.uint8)); alphas.append(a)
        quad = np.array([[60, 30], [260, 30], [260, 90], [60, 90]], float)
        info = {}
        tr = cv.track_plane(lambda i: frames[i], N, key, quad, lambda i: alphas[i], cv.TrackParams(smooth=0), info=info)
        self.assertGreaterEqual(len(tr), N - 2)
        for f, (c, conf) in tr.items():
            exp = quad - [3 * (f - key), 0]
            self.assertLess(np.abs(c - exp).max(), 2.5, f"frame {f}")
            d = cv.quad_drift(c, quad)
            self.assertLess(d["skew"], 3.0)
            self.assertLess(abs(d["area"] - 1), 0.05)

    def test_planar_track_occluder_crossing_quad_is_stable(self):
        """A subject walks right across the quad (covering most of it for several frames) while the wall pans:
        no frame is dropped, the quad keeps following the pan, and the trajectory has no per-frame jitter."""
        import cv2
        W, H, N, key = 320, 180, 48, 24
        yy, xx = np.mgrid[0:H + 40, 0:W + 240].astype(np.float32)
        wall = 140 + 30 * np.exp(-((xx - 220) ** 2) / (2 * 80 ** 2)) + np.random.default_rng(3).normal(0, 2.0, xx.shape)
        for x, y in [(30, 60), (90, 150), (170, 40), (240, 120), (330, 70), (410, 160), (500, 50)]:
            cv2.circle(wall, (x, y), 4, 100, -1)
        wall = cv2.GaussianBlur(wall, (0, 0), 1.0).clip(0, 255).astype(np.uint8)
        frames, alphas = [], []
        for t in range(N):
            fr = wall[20:20 + H, 2 * t:2 * t + W].copy()
            a = np.zeros((H, W), np.uint8)
            cv2.rectangle(a, (-60 + 9 * t, 10), (20 + 9 * t, H), 255, -1)  # 80 px wide, crosses the whole frame
            frames.append(np.where(a > 0, 25, fr).astype(np.uint8)); alphas.append(a)
        quad = np.array([[90, 40], [230, 40], [230, 120], [90, 120]], float)
        info = {}
        tr = cv.track_plane(lambda i: frames[i], N, key, quad, lambda i: alphas[i], cv.TrackParams(smooth=2), info=info)
        self.assertEqual(len(tr), N)
        self.assertGreater(info["occluded"], 3)
        err = np.array([np.abs(tr[f][0] - (quad - [2 * (f - key), 0])).max() for f in range(N)])
        self.assertLess(err.max(), 1.5)
        acc = np.array([np.abs(tr[f + 1][0] - 2 * tr[f][0] + tr[f - 1][0]).max() for f in range(1, N - 1)])
        self.assertLess(acc.max(), 0.5)  # second difference: no jitter

    def test_quad_drift_flags_skew_and_shrink(self):
        ref = np.array([[0, 0], [100, 0], [100, 50], [0, 50]], float)
        skewed = np.array([[-20, 5], [90, -10], [80, 30], [20, 70]], float)
        d = cv.quad_drift(skewed, ref)
        self.assertGreater(d["skew"], 20)
        self.assertLess(cv.quad_drift(ref * 0.5, ref)["area"], 0.3)

    def test_reframe_node_from_mask_and_preview(self):
        N, H, W = 24, 90, 160
        mask = torch.zeros(N, H, W)
        for t in range(N):
            mask[t, 20:90, 100 + t:130 + t] = 1  # subject on the right, drifting right
        images = torch.rand(N, H, W, 3)
        raw, prev = pack.TypesetReframeCrop().run("9:16", 24.0, mask=mask, images=images)
        doc = json.loads(raw)
        self.assertEqual(len(doc["frames"]), N)
        for fr in doc["frames"]:
            self.assertGreaterEqual(fr["x"], 0)
            self.assertLessEqual(fr["x"] + fr["w"], 1.00001)
        self.assertGreater(doc["frames"][-1]["x"], 0.4)       # moved toward the subject
        self.assertEqual(prev.shape[0], N)
        self.assertAlmostEqual(prev.shape[2] / prev.shape[1], 9 / 16, delta=0.05)

    def _person_left(self, n, W=1344, H=768):
        # Person standing at the left third for the whole clip.
        return {"tracks": [{"id": "person0", "frames": [{"f": f, "bbox": [0.2, 0.2, 0.12, 0.8], "cx": 0.26, "cy": 0.3}
                                                        for f in range(n)]}]}

    def test_focus_small_box_is_kept_in_frame(self):
        n, fps = 96, 24.0
        tracks = self._person_left(n)
        box = [0.62, 0.1, 0.72, 0.3]  # fits a 9:16 window (w = 0.321) together with nothing else
        base = cv.compute_crop(1344, 768, fps, tracks, None, "9:16", n)
        doc = cv.compute_crop(1344, 768, fps, tracks, None, "9:16", n, focus=[{"start": 1.0, "end": 3.0, "box": box}])
        for fr in doc["frames"]:
            self.assertAlmostEqual(fr["w"], base["frames"][0]["w"], places=5)  # never zooms when it fits
            if 24 <= fr["f"] < 72:
                self.assertLessEqual(fr["x"], box[0] - 0.02 + 1e-6)
                self.assertGreaterEqual(fr["x"] + fr["w"], box[2] + 0.02 - 1e-6)
        # Outside the range the person-following camera is untouched before the range.
        for a, b in zip(doc["frames"][:24], base["frames"][:24]):
            self.assertAlmostEqual(a["x"], b["x"], places=5)
        self.assertEqual(doc["focus"][0]["applied"], "follow")
        self.assertEqual((doc["focus"][0]["f0"], doc["focus"][0]["f1"]), (24, 72))

    def test_focus_wide_box_zooms_out_and_contains(self):
        n, fps = 60, 24.0
        box = [0.19, 0.05, 0.81, 0.31]  # the hero's LOUDER sign: wider than a 9:16 crop of 16:9
        doc = cv.compute_crop(1344, 768, fps, self._person_left(n), None, "9:16", n,
                              focus=[{"f0": 10, "f1": 40, "box": box}])
        for fr in doc["frames"]:
            if 10 <= fr["f"] < 40:
                self.assertLessEqual(fr["x"], box[0]); self.assertGreaterEqual(fr["x"] + fr["w"], box[2])
                self.assertLessEqual(fr["y"], box[1]); self.assertGreaterEqual(fr["y"] + fr["h"], box[3])
                self.assertAlmostEqual(fr["w"] * 1344 / (fr["h"] * 768), 9 / 16, places=3)  # aspect preserved
                self.assertGreater(fr["h"], 1.0)  # letterboxed
            else:
                self.assertLessEqual(fr["h"], 1.0)
        self.assertEqual(doc["focus"][0]["applied"], "zoom")

    def test_focus_pan_scans_left_to_right(self):
        n, fps = 60, 24.0
        box = [0.19, 0.05, 0.81, 0.31]
        doc = cv.compute_crop(1344, 768, fps, self._person_left(n), None, "9:16", n,
                              focus=[{"f0": 10, "f1": 40, "box": box, "mode": "pan"}])
        xs = [doc["frames"][f]["x"] for f in range(10, 40)]
        self.assertTrue(all(b >= a - 1e-9 for a, b in zip(xs, xs[1:])))
        self.assertAlmostEqual(xs[0], box[0] - 0.02, places=4)
        self.assertAlmostEqual(xs[-1] + doc["frames"][39]["w"], box[2] + 0.02, places=4)
        self.assertTrue(all(doc["frames"][f]["h"] <= 1.0 for f in range(n)))

    def test_reframe_node_focus_json_matches_core_and_letterboxes_preview(self):
        N, H, W = 30, 90, 160
        mask = torch.zeros(N, H, W)
        mask[:, 20:90, 20:50] = 1
        images = torch.rand(N, H, W, 3)
        focus = [{"f0": 5, "f1": 20, "box": [0.1, 0.1, 0.9, 0.3]}]
        raw, prev = pack.TypesetReframeCrop().run("9:16", 24.0, mask=mask, images=images, focus_json=json.dumps(focus))
        doc = json.loads(raw)
        tracks = json.loads(importlib.import_module("typeset_nodes.tracks").MaskToTracks().run(24.0, "person", mask=mask, track_id="person0")[0])
        self.assertEqual(doc, json.loads(json.dumps(cv.compute_crop(W, H, 24.0, tracks, None, "9:16", N, "person0", focus))))
        self.assertEqual(prev.shape[0], N)
        self.assertEqual(float(prev[10, 0, :, :].abs().sum()), 0.0)  # top letterbox row is black

    def test_focus_validation(self):
        with self.assertRaises(ValueError):
            cv.resolve_focus([{"start": 0, "end": 1, "box": [0.5, 0, 0.4, 1]}], 24, 48)
        with self.assertRaises(ValueError):
            cv.resolve_focus([{"start": 0, "end": 1, "box": [0, 0, 1, 1], "mode": "zoomy"}], 24, 48)
        self.assertEqual(cv.resolve_focus([{"start": 5, "end": 6, "box": [0, 0, 1, 1]}], 24, 48), [])

    def test_mask_tracks_in_chunks_equal_single_pass(self):
        tr = importlib.import_module("typeset_nodes.tracks").MaskToTracks()
        N, H, W = 50, 72, 128
        rng = np.random.default_rng(3)
        mask = torch.zeros(N, H, W)
        for t in range(N):
            if 20 <= t < 23:
                continue  # a gap: smoothing must not bleed across it
            x = int(10 + t * 1.5 + rng.integers(0, 4))
            mask[t, 15:70, x:x + 25] = 1
        whole = json.loads(tr.run(24.0, "person", mask=mask, smooth=5)[0])
        parts = [json.loads(tr.run(24.0, "person", mask=mask[a:a + 16], smooth=5, frame_offset=a, raw=True)[0])
                 for a in range(0, N, 16)]
        merged = cv.merge_track_chunks(parts, 24.0, N, smooth=5)
        self.assertEqual(json.dumps(merged, sort_keys=True), json.dumps(whole, sort_keys=True))

    def test_beat_grid_on_click_track(self):
        sr, bpm, dur = 22050, 120, 16.0
        y = np.zeros(int(sr * dur), np.float32)
        for i, t in enumerate(np.arange(0.5, dur, 60 / bpm)):
            n = int(t * sr)
            amp = 1.0 if i % 4 == 0 else 0.35  # accented downbeats
            click = amp * np.sin(2 * np.pi * (80 if i % 4 == 0 else 1500) * np.arange(800) / sr) * np.exp(-np.arange(800) / 150)
            y[n:n + 800] += click.astype(np.float32)
        g = beats.beat_grid(y, sr)
        self.assertAlmostEqual(g["bpm"], 120, delta=3)
        self.assertGreater(len(g["beats"]), 25)
        diffs = np.diff(g["downbeats"])
        self.assertTrue(np.allclose(diffs, 2.0, atol=0.1), diffs)
        self.assertAlmostEqual(g["downbeats"][0] % 2.0, 0.5, delta=0.1)
        self.assertEqual(g["sections"][0]["start"], 0.0)
        self.assertAlmostEqual(g["sections"][-1]["end"], dur, delta=0.01)
        img = beats.beat_grid_image(y, sr, g)
        self.assertEqual(img.shape, (240, 1280, 3))


if __name__ == "__main__":
    unittest.main()
