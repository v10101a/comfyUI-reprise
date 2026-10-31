"""v2 vision helpers: occupancy encoding, planar tracking on a synthetic moving plane, crop smoothing."""
import base64
import unittest

import numpy as np

from app import vision


class OccupancyTests(unittest.TestCase):
    def test_dims(self):
        self.assertEqual(vision.occupancy_dims(1344, 768), (32, 18))
        self.assertEqual(vision.occupancy_dims(768, 1344), (18, 32))
        self.assertEqual(vision.occupancy_dims(1080, 1080), (32, 32))

    def test_encoding_row_major_coverage(self):
        h, w = 180, 320
        alpha = np.zeros((h, w), np.uint8)
        alpha[:10, :10] = 255          # top-left cell fully covered
        alpha[170:, 310:] = 255        # bottom-right cell fully covered
        alpha[0:10, 20:25] = 255       # half of cell (row 0, col 2)
        cells = vision.occupancy_cells(alpha, 32, 18)
        self.assertEqual(cells.shape, (18, 32))
        raw = base64.b64decode(vision.encode_occupancy(cells))
        self.assertEqual(len(raw), 32 * 18)
        self.assertEqual(raw[0], 255)                  # first byte = top-left
        self.assertEqual(raw[-1], 255)                 # last byte = bottom-right
        self.assertTrue(120 <= raw[2] <= 135, raw[2])  # half covered ≈ 128
        self.assertEqual(raw[1], 0)
        np.testing.assert_array_equal(vision.decode_occupancy(vision.encode_occupancy(cells), 32, 18), cells)


def _texture(h, w, seed=0):
    rng = np.random.default_rng(seed)
    import cv2
    tex = rng.integers(0, 255, (h // 8, w // 8), dtype=np.uint8)
    tex = cv2.resize(tex, (w, h), interpolation=cv2.INTER_NEAREST)
    return cv2.GaussianBlur(tex, (3, 3), 0)


class TrackingTests(unittest.TestCase):
    def test_tracks_synthetic_moving_plane(self):
        import cv2
        W, H, N = 320, 240, 30
        plane = _texture(600, 800)
        def homography(t):
            # Pan + zoom + slight perspective that changes over time.
            s = 1 + 0.01 * t
            return np.array([[s, 0.02 * t / N, 40 + 3.0 * t], [0, s, 30 + 1.0 * t], [0.0002 * t / N, 0, 1]])
        # frame t shows plane point P at image point inv(G_t) P where G_t maps image→plane
        frames = [cv2.warpPerspective(plane, homography(t), (W, H), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)
                  for t in range(N)]
        key = 15
        quad = np.array([[100, 80], [220, 80], [220, 170], [100, 170]], float)
        # subject: a moving black blob that occludes part of the plane, with its matte
        alphas = []
        for t in range(N):
            a = np.zeros((H, W), np.uint8)
            cv2.circle(a, (60 + 6 * t, 120), 30, 255, -1)
            frames[t] = np.where(a > 0, 0, frames[t]).astype(np.uint8)
            alphas.append(a)
        track = vision.track_plane(lambda i: frames[i], N, key, quad, lambda i: alphas[i],
                                   vision.TrackParams(smooth=0))
        self.assertGreaterEqual(len(track), N - 2)
        Gk = homography(key)
        plane_quad = cv2.perspectiveTransform(quad.reshape(-1, 1, 2), Gk)
        for f in (0, 5, 25, N - 1):
            expect = cv2.perspectiveTransform(plane_quad, np.linalg.inv(homography(f))).reshape(4, 2)
            err = np.abs(track[f][0] - expect).max()
            self.assertLess(err, 1.5, f"frame {f}: corner error {err:.2f}px")
            self.assertGreater(track[f][1], 0.5)

    def test_smoothing_never_bridges_gaps(self):
        c = lambda v: (np.full((4, 2), float(v)), 1.0)
        tr = {0: c(0), 1: c(10), 2: c(20), 5: c(100)}
        sm = vision.smooth_corners(tr, 2)
        self.assertEqual(sm[5][0][0, 0], 100)
        self.assertTrue(0 < sm[0][0][0, 0] < 10)


class CropTests(unittest.TestCase):
    def test_crop_size(self):
        w, h = vision.crop_size(1344, 768, "9:16")
        self.assertAlmostEqual(h, 1.0)
        self.assertAlmostEqual(w * 1344 / (h * 768), 9 / 16, places=5)
        w, h = vision.crop_size(768, 1344, "16:9")
        self.assertAlmostEqual(w, 1.0)
        ow, oh = vision.output_size(1344, 768, "9:16")
        self.assertEqual((ow % 2, oh % 2), (0, 0))
        self.assertAlmostEqual(ow / oh, 9 / 16, places=2)

    def test_follow_stays_in_bounds_and_is_smooth(self):
        size = 0.32
        rng = np.random.default_rng(1)
        # jittery target that also runs off both edges, with a gap
        target = list(np.clip(np.linspace(-0.2, 1.2, 120) + rng.normal(0, 0.03, 120), -0.5, 1.5))
        target[50:60] = [None] * 10
        xs = vision.follow_axis(target, size, fps=24)
        self.assertEqual(len(xs), 120)
        self.assertTrue(all(size / 2 - 1e-9 <= x <= 1 - size / 2 + 1e-9 for x in xs))
        vel = np.diff(xs)
        self.assertLess(np.abs(vel).max(), 0.05)            # no jumps
        self.assertLess(np.abs(np.diff(vel)).max(), 0.01)    # no jitter (bounded acceleration)
        # dead zone: small wobble around a fixed point leaves the camera still
        still = vision.follow_axis([0.5 + 0.02 * np.sin(i) for i in range(48)], size, fps=24)
        self.assertLess(max(still) - min(still), 1e-6)

    def test_surface_bias(self):
        self.assertAlmostEqual(vision.surface_bias((0.4, 0.5), (0.25, 0.3), 0.32), 0.375)
        self.assertAlmostEqual(vision.surface_bias((0.4, 0.5), (0.9, 1.0), 0.32), 0.45)  # too wide: person wins


class EngineSelectionTests(unittest.TestCase):
    def test_comfy_failure_falls_back_and_says_so(self):
        from unittest import mock
        from app import analysis_v2
        with mock.patch.object(analysis_v2, "comfy_up", return_value=True):
            def boom():
                raise RuntimeError("node missing")
            doc, engine, note = analysis_v2.run_analysis("occupancy", "Occupancy", None, boom, lambda: {"ok": 1})
        self.assertEqual((doc, engine), ({"ok": 1}, "fallback"))
        self.assertIn("node missing", note)
        self.assertIn("in-process", note)
        with mock.patch.object(analysis_v2, "comfy_up", return_value=True):
            doc, engine, note = analysis_v2.run_analysis("occupancy", "Occupancy", None, lambda: ({"c": 1}, "abcdef123"), lambda: {})
        self.assertEqual(engine, "comfy")
        self.assertIn("occupancy.api.json", note)


class ReframeFocusTests(unittest.TestCase):
    def test_body_validation_and_shot_focus(self):
        from pydantic import ValidationError
        from app.models import ReframeBody, Project, GenShot
        from app.analysis_v2 import reframe_focus
        body = ReframeBody(aspect="9:16", focus=[{"start": 13.93, "end": 16.32, "box": [0.19, 0.05, 0.81, 0.31]}])
        self.assertEqual(body.focus[0].mode, "auto")
        for bad in ({"start": 2, "end": 1, "box": [0, 0, 1, 1]}, {"start": 0, "end": 1, "box": [0.5, 0, 0.4, 1]},
                    {"start": 0, "end": 1, "box": [0, 0, 1.2, 1]}, {"start": 0, "end": 1, "box": [0, 0, 1, 1], "mode": "zoom"}):
            with self.assertRaises(ValidationError):
                ReframeBody(aspect="9:16", focus=[bad])
        p = Project(id="p", name="p", shots=[GenShot(id="g1", start=1.0, end=2.0, focus=(0.1, 0.1, 0.9, 0.3)),
                                             GenShot(id="g2", start=3.0, end=4.0)])
        foc = reframe_focus(p, body.focus)
        self.assertEqual(len(foc), 2)
        self.assertEqual(foc[1], {"start": 1.0, "end": 2.0, "box": [0.1, 0.1, 0.9, 0.3], "mode": "auto", "label": "shot g1"})
        crop = vision.compute_crop(1344, 768, 24, None, None, "9:16", 48, focus=foc)
        self.assertEqual(crop["focus"][0]["applied"], "zoom")
        self.assertGreater(crop["frames"][30]["h"], 1.0)
        self.assertLessEqual(crop["frames"][10]["h"], 1.0)


if __name__ == "__main__":
    unittest.main()
