"""CPU checks for TypesetAlignLyrics that need no model weights (synthetic CTC emissions)."""
import importlib
import sys
import types
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.modules.setdefault("folder_paths", types.ModuleType("folder_paths"))
LA = importlib.import_module(f"{ROOT.name}.lyric_align")


class Normalize(unittest.TestCase):
    def test_words(self):
        self.assertEqual(LA.normalize_word("Hold"), "hold")
        self.assertEqual(LA.normalize_word("on,"), "on")
        self.assertEqual(LA.normalize_word("They’re"), "they're")
        self.assertEqual(LA.normalize_word("Café!"), "cafe")
        self.assertEqual(LA.normalize_word("'cause"), "cause")
        self.assertEqual(LA.normalize_word("24/7"), "twenty four seven")
        self.assertEqual(LA.normalize_word("1st"), "first")
        self.assertEqual(LA.normalize_word("—"), "")

    def test_tokens_skip_section_tags(self):
        lines, toks = LA.lyric_tokens("[verse]\nWalk me\n\n[chorus]\nHold on,")
        self.assertEqual(lines, ["Walk me", "Hold on,"])
        self.assertEqual([(li, t) for li, t, _ in toks], [(0, "Walk"), (0, "me"), (1, "Hold"), (1, "on,")])


class Align(unittest.TestCase):
    def synth(self, plan, frames=200):
        """Emission where each (char, frame) in plan is near-certain and everything else is blank."""
        from torchaudio.pipelines import MMS_FA
        d = MMS_FA.get_dict(star="*")
        em = torch.full((frames, len(d)), -20.0)
        em[:, 0] = -0.01
        em[:, d["*"]] = 0.0
        for c, f in plan:
            em[f, :] = -20.0
            em[f, d[c]] = -0.01
        return em

    def test_ctc_word_spans(self):
        toks = [(0, "ab", "ab"), (1, "cd", "cd")]
        em = self.synth([("a", 50), ("b", 52), ("c", 120), ("d", 125)])
        al = LA.ctc_align(em, toks)
        self.assertEqual((al[0][0], al[1][0]), (50, 120))
        self.assertGreater(al[0][2], 0.9)

    def test_too_short_counts_repeated_letters(self):
        toks = [(0, "ll", "ll")]
        with self.assertRaisesRegex(ValueError, "too short"):
            LA.ctc_align(self.synth([], frames=3), toks)  # * l - l * needs 5 frames
        self.assertIsNotNone(LA.ctc_align(self.synth([("l", 1), ("l", 3)], frames=5), toks)[0])

    def test_unalignable_word_is_interpolated(self):
        words = [{"text": "a", "start": 1.0, "end": 1.2}, {"text": "—", "start": None, "end": None},
                 {"text": "b", "start": 2.0, "end": 2.2}]
        LA._interpolate_missing(words)
        self.assertTrue(1.2 <= words[1]["start"] < words[1]["end"] <= 2.0)

    def test_nearest(self):
        import numpy as np
        self.assertAlmostEqual(LA.nearest(np.array([1.0, 2.0]), 1.94), 0.06)
        self.assertEqual(LA.nearest(np.array([]), 1.0), float("inf"))

    def test_reanchor_moves_line_that_would_hold_too_long(self):
        toks = [(0, "stop", "stop"), (0, "thinking", "thinking"), (1, "for", "for")]
        words = [{"start": 14.7, "end": 15.0, "ctcStart": 14.7}, {"start": 15.1, "end": 15.5, "ctcStart": 15.1},
                 {"start": 20.8, "end": 21.0, "ctcStart": 20.8}]
        calls = []
        def realign(idx, t0, t1):
            calls.append(t0)
            first = t0 if t0 < 18.0 else 18.26  # sticks to an early edge (no evidence), real evidence at 18.26
            return [(first, first + .3, .5), (first + .44, first + .8, .5)]
        LA._reanchor_lines(words, toks, runs=[], realign=realign, cap=2.5)
        self.assertAlmostEqual(words[0]["start"], 18.26)
        self.assertTrue(words[0]["reanchored"] and words[1]["reanchored"])
        self.assertEqual(words[2]["start"], 20.8)
        self.assertLess(calls[0], calls[-1])  # the window edge moved inward while the word sat on it

    def test_reanchor_respects_quiet_gaps(self):
        toks = [(0, "name", "name"), (1, "hold", "hold")]
        words = [{"start": 6.58, "end": 7.0, "ctcStart": 6.58}, {"start": 12.05, "end": 12.4, "ctcStart": 12.05}]
        LA._reanchor_lines(words, toks, runs=[(7.6, 11.8)], realign=lambda *a: self.fail("realigned"), cap=2.5)
        self.assertEqual(words[0]["start"], 6.58)

    def test_quiet_runs(self):
        import numpy as np
        rms = np.r_[np.ones(100), np.zeros(50) + .001, np.ones(100), np.zeros(10)]
        self.assertEqual(LA.quiet_runs(rms), [(1.0, 1.5)])

    def test_backends_registered(self):
        self.assertIn("hdemucs", LA.SEPARATORS)
        self.assertIn("mms_fa", LA.ALIGNERS)
        req = LA.TypesetAlignLyrics.INPUT_TYPES()["required"]
        self.assertEqual(req["separator"][0], list(LA.SEPARATORS))


if __name__ == "__main__":
    unittest.main()
