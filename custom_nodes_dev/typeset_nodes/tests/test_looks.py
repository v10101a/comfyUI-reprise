"""TypesetLook / TypesetGrade: preset sync with the web app, param patches, grade maths (CPU, no ComfyUI)."""
import importlib.util
import json
import unittest
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("typeset_looks", ROOT / "looks.py")
looks = importlib.util.module_from_spec(spec); spec.loader.exec_module(looks)
WEB = ROOT.parents[1] / "apps/web/src/look-presets.json"


class LookTests(unittest.TestCase):
    def test_presets_match_web_app(self):
        if not WEB.exists():
            self.skipTest("web app not in this checkout")
        self.assertEqual(json.loads(WEB.read_text()), looks.presets())

    def test_preset_fonts_are_bundled(self):
        for lid, e in looks.presets()["looks"].items():
            for role in ("hero", "body"):
                self.assertIn(e["look"]["font"][role], looks.FONT_FILES, f"{lid}.{role}")

    def test_picker_set(self):
        looks_ = looks.presets()["looks"]
        hidden = {k for k, v in looks_.items() if v.get("hidden")}
        self.assertEqual(hidden, {"dreamy", "grey-noise", "lens-bound"})  # kept for old projects, out of the picker
        self.assertEqual(looks_["graffiti"]["look"]["wall"], "spray")
        self.assertEqual(looks_["neon"]["look"]["finish"], "neon")
        ref = json.loads(looks.TypesetLook().run("graffiti", drips=.9)[0])
        self.assertEqual(ref["overrides"], {"drips": .9})
        ref = json.loads(looks.TypesetLook().run("neon", light=.3)[0])
        self.assertEqual(ref["overrides"], {"light": .3})

    def test_look_node_defaults_are_the_bare_preset(self):
        ref, preview = looks.TypesetLook().run("flat-card")
        self.assertEqual(json.loads(ref), {"id": "flat-card", "overrides": None})
        self.assertEqual(tuple(preview.shape), (1, 432, 768, 3))

    def test_look_node_params_become_overrides(self):
        ref = json.loads(looks.TypesetLook().run("paper-cut", accent="#00ff00", font="Inter", case="lower",
                                                 layout="stack", scale=1.5, glow=.4, cards="on", tubes="on")[0])
        o = ref["overrides"]
        self.assertEqual(o["palette"], {"accent": "#00ff00", "card": "#c8243a"} if "card" in o["palette"] else {"accent": "#00ff00"})
        self.assertEqual(o["font"], {"hero": "Inter", "heroCase": "lower", "bodyCase": "lower"})
        self.assertEqual((o["layout"], o["scale"], o["optics"], o["card"], o["finish"]), ("stack", 1.5, {"glow": .4}, True, "neon"))
        look = looks.resolve_look(ref)
        self.assertNotIn("heroWeight", look["font"])  # swapped face drops the preset weight
        self.assertEqual(look["palette"]["text"], "#efe6d2")

    def test_text_plate_takes_a_look(self):
        spec2 = importlib.util.spec_from_file_location("typeset_nodes.text_plate", ROOT / "text_plate.py",
                                                       submodule_search_locations=None)
        import sys, types
        pkg = types.ModuleType("typeset_nodes"); pkg.__path__ = [str(ROOT)]
        sys.modules.setdefault("typeset_nodes", pkg)
        sys.modules["typeset_nodes.looks"] = looks
        plate = importlib.util.module_from_spec(spec2); plate.__package__ = "typeset_nodes"; spec2.loader.exec_module(plate)
        img = torch.zeros(1, 90, 160, 3)
        out = plate.TypesetTextPlate().run(img, "hold", look_json=json.dumps({"id": "flat-card"}))[0]
        blue = (out[0, ..., 2] > .9) & (out[0, ..., 0] < .3)
        self.assertGreater(int(blue.sum()), 200)  # the flat blue card


class GradeTests(unittest.TestCase):
    def test_settings_match_grade_without_touching_frames(self):
        from unittest.mock import patch
        for grade in looks.GRADE_IDS():
            params = {"grade": grade, "amount": .7, "tint": "#ff77aa", "grain": .1, "halation": .4}
            with patch.object(looks, "grade_frames", side_effect=AssertionError("settings must not process images")):
                actual = json.loads(looks.TypesetGradeSettings().run(**params)[0])
            self.assertEqual(actual, looks.TypesetGrade.ref(**params))
        schema = looks.TypesetGradeSettings.INPUT_TYPES()["required"]
        self.assertNotIn("images", schema)
        self.assertNotIn("fps", schema)

    def frames(self):
        rng = np.random.default_rng(1)
        return rng.random((3, 32, 48, 3), dtype=np.float32)

    def test_none_and_zero_amount_are_identity(self):
        f = self.frames()
        self.assertIsNone(looks.resolve_grade({"id": "none"}))
        self.assertIsNone(looks.resolve_grade({"id": "teal", "amount": 0}))
        np.testing.assert_array_equal(looks.grade_frames(f, None), f)

    def test_mono_is_grey_and_xerox_keeps_red(self):
        f = self.frames(); f[0, :4, :4] = [1, 0, .2]
        m = looks.grade_frames(f, looks.resolve_grade({"id": "mono", "overrides": {"grain": 0}}))
        np.testing.assert_allclose(m[..., 0], m[..., 1], atol=1e-6)
        x = looks.grade_frames(f, looks.resolve_grade({"id": "xerox", "overrides": {"grain": 0}}))
        self.assertGreater(float(x[0, 0, 0, 0] - x[0, 0, 0, 1]), .5)

    def test_flash_brightens_on_the_downbeat(self):
        f = np.full((2, 8, 8, 3), .3, np.float32)
        g = looks.resolve_grade({"id": "xerox", "overrides": {"grain": 0}})
        out = looks.grade_frames(f, g, fps=10, beats={"beats": [0.0], "downbeats": [0.0]})
        self.assertGreater(float(out[0].mean()), float(out[1].mean()))

    def test_tint_keeps_luminance_and_amount_scales(self):
        f = self.frames()
        g1 = looks.grade_frames(f, looks.resolve_grade({"id": "teal", "overrides": {"grain": 0}}))
        g5 = looks.grade_frames(f, looks.resolve_grade({"id": "teal", "amount": .5, "overrides": {"grain": 0}}))
        d1, d5 = np.abs(g1 - f).mean(), np.abs(g5 - f).mean()
        self.assertLess(d5, d1)
        self.assertLess(abs(float(looks._lum(g1).mean() - looks._lum(f).mean())), .12)

    def test_grade_node_outputs_project_grade(self):
        imgs, ref = looks.TypesetGrade().run(torch.from_numpy(self.frames()), "film", .7, grain=0.0, seed=3)
        self.assertEqual(json.loads(ref), {"id": "film", "amount": .7, "overrides": {"grain": 0.0}})
        self.assertEqual(tuple(imgs.shape), (3, 32, 48, 3))
        a = looks.TypesetGrade().run(torch.from_numpy(self.frames()), "film", 1.0, seed=3)[0]
        b = looks.TypesetGrade().run(torch.from_numpy(self.frames()), "film", 1.0, seed=3)[0]
        self.assertTrue(torch.equal(a, b))  # deterministic grain


if __name__ == "__main__":
    unittest.main()
