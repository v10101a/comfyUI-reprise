"""Offline tests for the remote MiniMax path: sizes, the reference graph, prompts, edit focus."""
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from pydantic import ValidationError

from app import remote_gen as rg
from app.models import InworldBody


class RemoteGenTests(unittest.TestCase):
    def test_direction_keeps_exact_text_and_motion_in_their_model_prompts(self):
        text = "Stay again!"
        appearance = "Copper letters on concrete. Keep the existing light."
        motion = "The camera holds still. Hair moves in a light breeze. Lips closed."
        edit = rg.edit_prompt(text, appearance)
        self.assertIn(f'"{text}"', edit)
        self.assertIn("Lettering and setting: " + appearance, edit)
        self.assertNotIn(motion, edit)
        for prompt in (rg.motion_prompt(text, appearance, motion), rg.ref_prompt(text, appearance, motion)):
            self.assertIn(f'"{text}"', prompt)
            self.assertIn(motion, prompt)
            self.assertIn("<Picture 1>", prompt)
        self.assertEqual(InworldBody(start=0, end=2, seed=0).seed, 0)
        for seed in (-1, 2147483648, 1.2):
            with self.assertRaises(ValidationError):
                InworldBody(start=0, end=2, seed=seed)

    def test_sizes(self):
        self.assertEqual(rg.gen_size(1344, 768, 1344), (1344, 768))
        self.assertEqual(rg.gen_size(1344, 768, 1024), (1024, 576))
        self.assertEqual(rg.gen_size(1920, 1080, 736), (736, 416))
        with self.assertRaises(ValidationError):
            InworldBody(start=0, end=1, longEdge=2048)
        self.assertEqual(InworldBody(start=0, end=1, longEdge=1344).longEdge, 1344)

    def test_reference_graph_matches_hero_script(self):
        g = rg.minimax_ref_graph("ref.png", "The woman from <Picture 1>", 1344, 768, 124, 7, "pre", "first.png")
        by = {v["class_type"]: (k, v) for k, v in g.items()}
        self.assertNotIn("MiniMaxH3ImageToVideo", by)
        rk, ref = by["MiniMaxH3ReferenceToVideo"]
        self.assertEqual((ref["inputs"]["width"], ref["inputs"]["height"], ref["inputs"]["length"]), (1344, 768, 124))
        self.assertEqual(g[ref["inputs"]["ref_images.ref_image_1"][0]]["inputs"]["image"], "ref.png")
        self.assertEqual(g[ref["inputs"]["audio_vae"][0]]["class_type"], "VAELoader")
        gk, guide = by["MiniMaxH3AddGuide"]
        self.assertEqual(guide["inputs"]["positive"], [rk, 0])
        self.assertEqual(g[guide["inputs"]["image"][0]]["inputs"]["image"], "first.png")
        self.assertEqual(by["BasicGuider"][1]["inputs"]["conditioning"], [gk, 0])
        self.assertEqual(by["SamplerCustomAdvanced"][1]["inputs"]["latent_image"], [rk, 1])
        # Without a first frame: pure reference-to-video, sampled straight from the reference node.
        g2 = rg.minimax_ref_graph("ref.png", "p", 768, 1344, 124, 7, "pre")
        self.assertFalse(any(v["class_type"] == "MiniMaxH3AddGuide" for v in g2.values()))
        samp = next(v for v in g2.values() if v["class_type"] == "SamplerCustomAdvanced")
        self.assertEqual(g2[samp["inputs"]["latent_image"][0]]["class_type"], "MiniMaxH3ReferenceToVideo")

    def test_ref_prompt(self):
        own = "The woman from <Picture 1> walks through rain."
        self.assertEqual(rg.ref_prompt("LOUDER", "", own), own)
        p = rg.ref_prompt("LOUDER", "as a neon sign", None)
        self.assertIn("<Picture 1>", p)
        self.assertIn('"LOUDER" as a neon sign', p)

    def test_edit_focus_finds_added_word_despite_relight(self):
        rng = np.random.default_rng(1)
        frame = (rng.integers(20, 60, (288, 512, 3))).astype(np.uint8)
        frame = cv2.GaussianBlur(frame, (0, 0), 4)
        plate = np.clip(frame.astype(int) + [40, 0, 50], 0, 255).astype(np.uint8)  # global magenta relight
        cv2.putText(plate, "LOUD", (100, 70), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 80, 255), 6)
        cv2.circle(plate, (256, 60), 25, (40, 60, 90), -1)  # a head in front of the sign splits it
        cv2.putText(plate, "ER", (300, 70), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 80, 255), 6)
        with tempfile.TemporaryDirectory() as d:
            fa, pb = Path(d, "f.png"), Path(d, "p.png")
            cv2.imwrite(str(fa), frame)
            cv2.imwrite(str(pb), cv2.resize(plate, (400, 225)))  # the plate can be another size
            box = rg.edit_focus(fa, pb)
        self.assertIsNotNone(box)
        x0, y0, x1, y1 = box
        self.assertLess(x0, 100 / 512 + 0.03)
        self.assertGreater(x1, 370 / 512 - 0.03)
        self.assertLess(y0, 30 / 288)
        self.assertLess(y1, 0.5)


if __name__ == "__main__":
    unittest.main()
