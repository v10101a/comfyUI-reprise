"""Bring-your-own workflow import/mapping (no ComfyUI needed: the registry is stubbed)."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock

TMP = tempfile.TemporaryDirectory()
os.environ.setdefault("TYPESET_DATA_DIR", TMP.name)

from fastapi.testclient import TestClient  # noqa: E402
from app import workflows  # noqa: E402
from app.main import app  # noqa: E402

REGISTRY = {
    "LoadImage": {"input": {"required": {"image": [["a.png"], {"image_upload": True}]}}},
    "CLIPTextEncode": {"input": {"required": {"text": ["STRING", {"multiline": True}], "clip": ["CLIP"]}}},
    "KSampler": {"input": {"required": {"seed": ["INT", {"min": 0}], "steps": ["INT", {"min": 1, "max": 100}], "cfg": ["FLOAT", {}]}}},
    "SaveImage": {"input": {"required": {"images": ["IMAGE"], "filename_prefix": ["STRING", {}]}}, "output_node": True},
}
GRAPH = {
    "1": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "a sky", "clip": ["9", 0]}, "_meta": {"title": "Positive"}},
    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry", "clip": ["9", 0]}, "_meta": {"title": "Negative"}},
    "4": {"class_type": "KSampler", "inputs": {"seed": 5, "steps": 20, "cfg": 7.0}},
    "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0], "filename_prefix": "x"}},
}


class WorkflowImport(unittest.TestCase):
    def setUp(self):
        self.registry = patch.object(workflows, "object_info", side_effect=lambda force=False, remote=False: REGISTRY)
        self.registry.start()
        self.addCleanup(self.registry.stop)
        remote = patch.object(workflows, "remote_runner", None)
        remote.start()
        self.addCleanup(remote.stop)
        self.c = TestClient(app)

    def test_import_suggests_mapping_and_rejects_ui_format(self):
        r = self.c.post("/api/workflows", json={"graph": {"prompt": GRAPH}, "name": "sky"})
        self.assertEqual(r.status_code, 200, r.text)
        wf = r.json()
        self.assertEqual(set(wf["inputs"]), {"media", "prompt", "seed"})
        self.assertEqual(wf["inputs"]["prompt"]["node"], "2")
        self.assertEqual(wf["output"], {"node": "5", "type": "image"})
        self.assertEqual(wf["missing"], [])
        self.assertEqual(self.c.post("/api/workflows", json={"graph": {"nodes": [], "links": []}}).status_code, 422)
        wf = self.c.put(f"/api/workflows/{wf['id']}", json={"inputs": {"steps": {"node": "4", "field": "steps"}}}).json()
        self.assertEqual(wf["inputs"]["steps"]["max"], 100)
        self.assertEqual(self.c.put(f"/api/workflows/{wf['id']}", json={"output": {"node": "99"}}).status_code, 422)
        self.assertEqual(self.c.post(f"/api/workflows/{wf['id']}/delete").status_code, 200)
        self.assertEqual(self.c.get(f"/api/workflows/{wf['id']}").status_code, 404)

    def test_missing_nodes_block_runs(self):
        wf = self.c.post("/api/workflows", json={"graph": {**GRAPH, "6": {"class_type": "NotInstalled", "inputs": {}}}}).json()
        self.assertEqual(wf["missing"], ["NotInstalled"])
        pid = self.c.post("/api/projects", json={"name": "t"}).json()["id"]
        r = self.c.post(f"/api/projects/{pid}/workflows/{wf['id']}/run", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c.put("/api/session", json={"projectId": pid}).json()["projectId"], pid)

    def test_missing_models_block_local_run_and_refresh_after_install(self):
        registry = {**REGISTRY, "UNETLoader": {"input": {"required": {"unet_name": [[], {}]}}}}
        workflows.object_info.side_effect = lambda force=False, remote=False: registry
        wf = self.c.post("/api/workflows", json={"graph": {**GRAPH, "6": {
            "class_type": "UNETLoader", "inputs": {"unet_name": "video.safetensors"}}}}).json()
        self.assertEqual(wf["missingModels"], ["video.safetensors"])
        pid = self.c.post("/api/projects", json={"name": "t"}).json()["id"]
        r = self.c.post(f"/api/projects/{pid}/workflows/{wf['id']}/run", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("missing models", r.json()["detail"])
        registry["UNETLoader"]["input"]["required"]["unet_name"][0].append("video.safetensors")
        self.assertEqual(self.c.get(f"/api/workflows/{wf['id']}").json()["missingModels"], [])

    def test_remote_ready_workflow_is_not_blocked_by_local_models_or_nodes(self):
        remote_registry = {**REGISTRY, "RemoteVideo": {"input": {"required": {"unet_name": [["video.safetensors"], {}]}}}}
        workflows.object_info.side_effect = lambda force=False, remote=False: remote_registry if remote else REGISTRY
        with patch.object(workflows, "remote_runner", SimpleNamespace(comfyui_url="http://gpu")):
            wf = self.c.post("/api/workflows", json={"graph": {**GRAPH, "6": {
                "class_type": "RemoteVideo", "inputs": {"unet_name": "video.safetensors"}}}}).json()
            self.assertEqual(wf["target"], "remote")
            self.assertEqual(wf["missing"], [])
            self.assertEqual(wf["missingModels"], [])
            pid = self.c.post("/api/projects", json={"name": "t"}).json()["id"]
            from app import service
            with patch.object(workflows, "run_workflow", return_value={}) as run:
                fake = SimpleNamespace(require_project=service.require_project, jobs=Mock())
                fake.jobs.submit.side_effect = lambda job, fn: fn(None)
                workflows.run_job(fake, pid, wf["id"], {})
                self.assertTrue(run.call_args.args[3]["remote"], "The checked target must be pinned into the job")
            # Explicit local requests still fail against the local registry.
            r = self.c.post(f"/api/projects/{pid}/workflows/{wf['id']}/run", json={"remote": False})
            self.assertEqual(r.status_code, 400)
            # Remote requests cannot bypass missing remote models.
            remote_registry["RemoteVideo"]["input"]["required"]["unet_name"][0].clear()
            r = self.c.post(f"/api/projects/{pid}/workflows/{wf['id']}/run", json={"remote": True})
            self.assertEqual(r.status_code, 400)
            self.assertIn("missing models", r.json()["detail"])

    def test_ready_local_workflow_stays_local(self):
        with patch.object(workflows, "remote_runner", SimpleNamespace(comfyui_url="http://gpu")):
            wf = self.c.post("/api/workflows", json={"graph": GRAPH}).json()
            self.assertEqual(wf["target"], "local")
            self.assertFalse(any(c.kwargs.get("remote") for c in workflows.object_info.call_args_list))

    def test_unconfigured_remote_and_unreachable_host_fail_before_queueing(self):
        wf = self.c.post("/api/workflows", json={"graph": GRAPH}).json()
        pid = self.c.post("/api/projects", json={"name": "t"}).json()["id"]
        url = f"/api/projects/{pid}/workflows/{wf['id']}/run"
        r = self.c.post(url, json={"remote": True})
        self.assertEqual(r.status_code, 400)
        self.assertIn("not configured", r.json()["detail"])
        workflows.object_info.side_effect = lambda **kwargs: {}
        self.assertTrue(self.c.get(f"/api/workflows/{wf['id']}").json()["readinessError"])
        self.assertEqual(self.c.post(url, json={}).status_code, 503)


class WorkflowRegistry(unittest.TestCase):
    def test_cache_is_per_host_and_does_not_reuse_stale_readiness_on_failure(self):
        with patch.dict(workflows._registries, {}, clear=True), patch.object(workflows, "remote_runner", SimpleNamespace(comfyui_url="http://gpu")), patch.object(workflows.httpx, "get") as get:
            get.return_value.json.side_effect = [REGISTRY, {"RemoteOnly": {}}]
            self.assertEqual(workflows.object_info(), REGISTRY)
            self.assertEqual(workflows.object_info(remote=True), {"RemoteOnly": {}})
            self.assertEqual(workflows.object_info(), REGISTRY)
            self.assertEqual(get.call_count, 2)
            get.side_effect = RuntimeError("offline")
            self.assertEqual(workflows.object_info(force=True, remote=True), {})
            self.assertEqual(workflows.object_info(remote=True), {})
            self.assertEqual(workflows.object_info(), REGISTRY)

    def test_load_audio_is_an_audio_media_input(self):
        """Audio-driven graphs (S2V, lip-sync): LoadAudio is a media input staged from the song window."""
        registry = {**REGISTRY, "LoadAudio": {"input": {"required": {"audio": [["x.wav"], {"audio_upload": True}]}}}}
        graph = {**GRAPH, "6": {"class_type": "LoadAudio", "inputs": {"audio": "x.wav"}}}
        cands = workflows.candidates(graph, registry)
        audio = [c for c in cands["inputs"] if c["node"] == "6"]
        self.assertEqual(len(audio), 1)
        self.assertEqual((audio[0]["role"], audio[0]["kind"], audio[0]["media"]), ("media", "comfy_input_path", "audio"))
        plain = workflows.candidates({"6": {"class_type": "LoadAudio", "inputs": {"audio": "x.wav"}}}, {})  # no registry: class name
        self.assertEqual(plain["inputs"][0]["media"], "audio")


if __name__ == "__main__":
    unittest.main()
