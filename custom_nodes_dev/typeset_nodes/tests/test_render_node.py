"""TypesetRender: renderer selection and the automatic draft fallback (CPU, no ComfyUI, no browser)."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
PKG = "typeset_nodes_under_test"
if PKG not in sys.modules:  # load the pack as a package (relative imports) without its ComfyUI __init__
    spec = importlib.util.spec_from_file_location(PKG, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = pkg
render_node = importlib.import_module(f"{PKG}.render_node")
browser_render = importlib.import_module(f"{PKG}.browser_render")

WORDS = json.dumps({"words": [{"text": "hold", "start": 0.0, "end": 0.3, "lineId": "l0"},
                              {"text": "on", "start": 0.3, "end": 0.6, "lineId": "l0"}]})
PROMPT = {"9": {"class_type": "TypesetRender", "inputs": {"images": ["1", 0], "look_json": ["7", 0]}},
          "11": {"class_type": "SaveImage", "inputs": {"images": ["9", 0]}}}


class RenderNodeTests(unittest.TestCase):
    def setUp(self):
        self.images = torch.full((6, 64, 96, 3), .3)

    def test_draft_runs_and_says_so(self):
        out = render_node.TypesetRender().run(self.images, WORDS, 12.0, renderer="draft")
        images, text, info = out["result"]
        self.assertEqual(tuple(images.shape), (6, 64, 96, 3))
        self.assertTrue(info.startswith("draft"), info)
        self.assertGreater(float((images - self.images).abs().max()), 0)  # type was drawn

    def test_auto_falls_back_when_no_studio_host(self):
        if "typeset_server.service" in sys.modules:
            self.skipTest("studio host loaded in this process")
        self.assertIsNotNone(browser_render.unavailable())
        info = render_node.TypesetRender().run(self.images, WORDS, 12.0)["result"][2]
        self.assertIn("draft", info)
        self.assertIn("studio host is not mounted", info)

    def test_studio_required_raises_when_unavailable(self):
        if "typeset_server.service" in sys.modules:
            self.skipTest("studio host loaded in this process")
        with self.assertRaises(RuntimeError):
            render_node.TypesetRender().run(self.images, WORDS, 12.0, renderer="studio")

    def test_links_from_hidden_prompt(self):
        self.assertTrue(render_node._linked(PROMPT, "9", output=0))
        self.assertFalse(render_node._linked(PROMPT, "9", output=1))
        self.assertTrue(render_node._linked(PROMPT, "9", input_name="look_json"))
        self.assertFalse(render_node._linked(PROMPT, "9", input_name="grade_json"))
        self.assertIsNone(render_node._linked(None, "9", output=1))


if __name__ == "__main__":
    unittest.main()
