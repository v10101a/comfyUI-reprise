"""Comfy Cloud generation host: SDK-native uploads, keyed REST preflight/health; no network required."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import httpx

from app.comfy import ASSET_SCHEME, ComfyRunner, WorkflowInputError, WorkflowRunError, Sidecar, SidecarInput


def response(data, status=200):
    return httpx.Response(status, json=data, request=httpx.Request("GET", "https://cloud.comfy.org/api/x"))


class FakeAsset:
    _is_comfy_asset = True

    def __init__(self, path):
        self.file_path = str(path)
        self.id = None
        self.created_new = True

    def commit(self):
        self.id = "a1b2"
        return self.id


class CloudRunnerTests(unittest.TestCase):
    def cloud(self):
        return ComfyRunner(base_url="https://cloud.comfy.org", comfyui_url="https://cloud.comfy.org/api", api_key="comfyui-test", cloud=True)

    def test_cloud_is_remote_sdk_only_with_keyed_headers(self):
        run = self.cloud()
        self.assertTrue(run.remote)
        self.assertFalse(run.direct)
        self.assertEqual(run.api_headers, {"X-API-Key": "comfyui-test"})
        self.assertIsNone(ComfyRunner(base_url="http://127.0.0.1:8190", comfyui_url="http://remote:8188", remote=True).api_headers)

    def test_stage_uploads_through_sdk_assets_and_bind_substitutes_handle(self):
        run = self.cloud()
        uploads = []
        fake_client = SimpleNamespace(assets=SimpleNamespace(from_file=lambda p: uploads.append(p) or FakeAsset(p)))
        with tempfile.TemporaryDirectory() as tmp, patch.object(ComfyRunner, "client", return_value=fake_client):
            img = Path(tmp) / "plate.png"
            img.write_bytes(b"png")
            ref = run.stage_image(img, "proj", "shot", "plate.png")
            self.assertEqual(ref, f"{ASSET_SCHEME}a1b2")
            self.assertEqual(uploads, [img])
            sidecar = Sidecar(name="t", path=Path(tmp) / "t.inputs.json", workflow_path=Path(tmp) / "t.api.json", description="",
                              inputs={"image": SidecarInput(node="1", field="image", kind="comfy_input_path"),
                                      "seed": SidecarInput(node="2", field="seed", kind="int")}, outputs={})
            graph = {"1": {"class_type": "LoadImage", "inputs": {}}, "2": {"class_type": "KSampler", "inputs": {}}}
            set_calls = []
            run._bind(sidecar, {"image": ref, "seed": "7"}, graph, lambda n, f, v: set_calls.append((n, f, v)))
            self.assertIs(set_calls[0][2], run._assets["a1b2"])  # the SDK handle, not the placeholder string
            self.assertEqual(set_calls[1], ("2", "seed", 7))
            # A bare local file is uploaded on the fly; anything else is refused before submit.
            run._bind(sidecar, {"image": str(img), "seed": 1}, graph, lambda n, f, v: set_calls.append((n, f, v)))
            self.assertEqual(len(uploads), 2)
            with self.assertRaises(WorkflowInputError):
                run._bind(sidecar, {"image": "typeset/p/missing.png", "seed": 1}, graph, lambda *a: None)

    def test_unknown_asset_id_becomes_plain_reference(self):
        ref = self.cloud()._cloud_input(f"{ASSET_SCHEME}zzz", "image")
        self.assertEqual(ref, {"__type": "core/ASSET", "info": {"id": "zzz"}})

    def test_preflight_uses_keyed_object_info_without_proxy_check(self):
        run = self.cloud()
        registry = {"UNETLoader": {"input": {"required": {"unet_name": [["hosted.safetensors"]]}}}}
        graph = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "hosted.safetensors"}},
                 "2": {"class_type": "VHS_VideoCombine", "inputs": {}}}
        with patch("app.comfy.httpx.get", return_value=response(registry)) as get:
            with self.assertRaisesRegex(WorkflowRunError, "Comfy Cloud does not host.*VHS_VideoCombine"):
                run.preflight_graph(graph)
            run.preflight_graph({"1": graph["1"]})  # cached registry: still one HTTP call
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.args[0], "https://cloud.comfy.org/api/object_info")
        self.assertEqual(get.call_args.kwargs["headers"], {"X-API-Key": "comfyui-test"})
        with patch("app.comfy.httpx.get", return_value=response({}, 401)):
            with self.assertRaisesRegex(WorkflowRunError, "rejected the API key"):
                self.cloud().preflight_graph(graph)

    def test_health_hits_cloud_endpoints_with_key(self):
        calls = []
        def get(url, **kw):
            calls.append((url, kw.get("headers")))
            return response({"queue_running": [1], "queue_pending": []}) if url.endswith("/queue") else response({"ok": True})
        with patch("app.comfy.httpx.get", side_effect=get):
            out = self.cloud().health()
        self.assertEqual(out["host"], "cloud")
        self.assertTrue(out["proxy"] and out["comfyui"])
        self.assertEqual(out["queue"], {"running": 1, "pending": 0})
        self.assertEqual([u for u, _ in calls], ["https://cloud.comfy.org/api/v2/health", "https://cloud.comfy.org/api/queue"])
        self.assertTrue(all(h == {"X-API-Key": "comfyui-test"} for _, h in calls))

    def test_history_fallback_is_skipped_on_cloud(self):
        with patch("app.comfy.httpx.get", side_effect=AssertionError("no /history on Cloud")):
            self.assertIsNone(self.cloud()._history_text("job", "3"))


if __name__ == "__main__":
    unittest.main()
