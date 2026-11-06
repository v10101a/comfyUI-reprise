"""ComfyUI-backed jobs are refused up front with a clear message when ComfyUI is unreachable."""
import io
import os
import tempfile
import unittest
from unittest.mock import patch

TMP = tempfile.TemporaryDirectory()
os.environ.setdefault("TYPESET_DATA_DIR", TMP.name)

from fastapi.testclient import TestClient
from PIL import Image
from app import service
from app.main import app


class RequireComfyTests(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)
        self.pid = self.c.post('/api/projects', json={'name': 'Require comfy'}).json()['id']
        b = io.BytesIO(); Image.new('RGB', (80, 48), '#ea2030').save(b, format='PNG')
        asset = self.c.post(f'/api/projects/{self.pid}/assets', files={'file': ('face.png', b.getvalue(), 'image/png')}).json()
        p = self.c.get(f'/api/projects/{self.pid}').json()
        p.update(width=160, height=90, fps=24, duration=4, layers=[dict(id='shot', kind='media', assetId=asset['id'], start=1, **{'in': 0}, out=2)])
        self.c.put(f'/api/projects/{self.pid}', json=p).raise_for_status()

    def test_matte_refused_when_comfyui_down(self):
        down = {"proxy": False, "comfyui": False, "proxyUrl": "http://127.0.0.1:8189", "comfyuiUrl": "http://127.0.0.1:8188", "transport": "sdk"}
        with patch.dict(os.environ, {"TYPESET_ANALYSIS_ENGINE": "comfy"}), patch.object(service.runner, 'health', return_value=down), \
             patch.object(service.jobs, 'submit', side_effect=AssertionError('must not queue')):
            r = self.c.post(f'/api/projects/{self.pid}/analyze/matte', json={'layerId': 'shot'})
        self.assertEqual(r.status_code, 503, r.text)
        self.assertIn('scripts/comfy.sh start', r.json()['detail'])
        self.assertIn('8188', r.json()['detail'])

    def test_matte_queued_when_comfyui_up(self):
        up = {"proxy": True, "comfyui": True, "proxyUrl": "http://127.0.0.1:8189", "comfyuiUrl": "http://127.0.0.1:8188", "transport": "sdk"}
        with patch.dict(os.environ, {"TYPESET_ANALYSIS_ENGINE": "comfy"}), patch.object(service.runner, 'health', return_value=up), \
             patch.object(service.jobs, 'submit', side_effect=lambda job, fn: job):
            r = self.c.post(f'/api/projects/{self.pid}/analyze/matte', json={'layerId': 'shot'})
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == '__main__':
    unittest.main()
