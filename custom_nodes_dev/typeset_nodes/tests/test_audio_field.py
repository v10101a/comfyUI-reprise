"""TypesetAudioField: low-band pulse follows the kick, ignores the highs, never jumps down (CPU, numpy only)."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audio_field", ROOT / "audio_field.py")
af = importlib.util.module_from_spec(spec)
spec.loader.exec_module(af)


def kicks(sr=22050, seconds=4.0, bpm=120, hat=True):
    t = np.arange(int(sr * seconds)) / sr
    y = np.zeros_like(t)
    for k in np.arange(0, seconds, 60 / bpm):
        m = (t >= k) & (t < k + .15)
        y[m] += np.sin(2 * np.pi * 60 * (t[m] - k)) * np.exp(-(t[m] - k) / .05)
    if hat:  # loud, constant high content must not move the field
        y += .5 * np.sin(2 * np.pi * 3000 * t)
    return y.astype(np.float32), sr


class AudioFieldTests(unittest.TestCase):
    def test_pulses_on_the_kick(self):
        y, sr = kicks()
        d = af.band_doc(y, sr, 24.0)
        lv = np.array(d["level"])
        self.assertEqual(d["kind"], "bass")
        self.assertEqual(d["frames"], 96)
        self.assertEqual(d["band"], [40.0, 140.0])
        self.assertTrue(((lv >= 0) & (lv <= 1)).all())
        # Kick every 0.5 s = 12 frames: a hit, then the trough just before the next one.
        for k in range(1, 7):
            f = 12 * k
            self.assertGreater(lv[f - 1:f + 2].max(), lv[f - 2] + .3)

    def test_hits_on_the_kick_never_after(self):
        """Kicks at times that don't line up with frames: the peak lands on the kick's frame or one frame early."""
        sr, fps = 22050, 24.0
        t = np.arange(int(sr * 6)) / sr
        y = .03 * np.sin(2 * np.pi * 80 * t)
        onsets = np.arange(.3, 5.7, .4567)
        for k in onsets:
            m = (t >= k) & (t < k + .2)
            y[m] += np.sin(2 * np.pi * 55 * (t[m] - k)) * np.exp(-(t[m] - k) / .06)
        lv = np.array(af.band_doc(y.astype(np.float32), sr, fps)["level"])
        for k in onsets:
            f = int(k * fps)
            delay = int(np.argmax(lv[f - 3:f + 8])) - 3
            self.assertIn(delay, (-1, 0), f"kick at {k:.3f}s peaks {delay:+d} frames from its frame")
            self.assertGreater(lv[f] - lv[f - 2], .3)  # already up on the kick's own frame

    def test_release_is_smooth(self):
        y, sr = kicks()
        lv = np.array(af.band_doc(y, sr, 24.0, release_ms=250)["level"])
        # One-pole release at 250 ms: a frame (41.7 ms) can drop at most ~16% of the range (+ peak hold slack).
        self.assertLess(np.max(lv[:-1] - lv[1:]), .2)

    def test_band_ignores_highs(self):
        y, sr = kicks(hat=False)
        t = np.arange(len(y)) / sr
        y = y + .05 * np.sin(2 * np.pi * 80 * t).astype(np.float32)  # quiet bass bed: a real floor, not digital silence
        hats = (np.sin(2 * np.pi * 3000 * t) * (.5 + .5 * np.sin(2 * np.pi * 4 * t)) ** 4).astype(np.float32)  # click-free
        a = np.array(af.band_doc(y, sr, 24.0)["level"])
        b = np.array(af.band_doc(y + .5 * hats, sr, 24.0)["level"])
        self.assertLess(np.abs(a - b).max(), .05)


if __name__ == "__main__":
    unittest.main()
