"""Layer matte API, source staging, and race protection; no model or remote calls."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TMP = tempfile.TemporaryDirectory()
os.environ.setdefault("TYPESET_DATA_DIR", TMP.name)
os.environ["TYPESET_ANALYSIS_ENGINE"] = "local"

from fastapi.testclient import TestClient
from PIL import Image
from app import pipeline, service
from app.main import app
from app.matte_source import matte_source
from app.comfy import RunResult
from app.media import ffmpeg, extract_frame, ffprobe_frames


class Ctx:
    id = "layer_matte_test"
    def progress(self, *args, **kwargs): pass


class LayerMatteTests(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)
        self.p = self.c.post('/api/projects', json={'name': 'Layer matte test'}).json()
        self.pid = self.p['id']
        b = io.BytesIO(); Image.new('RGB', (80, 48), '#ea2030').save(b, format='PNG')
        self.asset = self.c.post(f'/api/projects/{self.pid}/assets', files={'file': ('face.png', b.getvalue(), 'image/png')}).json()
        self.p = self.c.get(f'/api/projects/{self.pid}').json()
        self.p.update(width=160, height=90, fps=24, duration=4, layers=[dict(id='shot', kind='media', assetId=self.asset['id'], start=1, **{'in': 0}, out=2, transform={'x': .2, 'scale': .8})])
        self.c.put(f'/api/projects/{self.pid}', json=self.p).raise_for_status()

    def test_api_accepts_layer_only_and_pins_source_before_queue(self):
        with patch.object(service.jobs, 'submit', side_effect=lambda job, fn: job) as submit:
            r = self.c.post(f'/api/projects/{self.pid}/analyze/matte', json={'layerId': 'shot'})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()['layerId'], 'shot')
            fn = submit.call_args.args[1]
            service.store.update(self.pid, lambda p: p.layers[0].update(assetId='missing'))
            with self.assertRaisesRegex(ValueError, 'asset|source'):
                fn(Ctx())
        self.assertEqual(self.c.post(f'/api/projects/{self.pid}/analyze/matte', json={}).status_code, 400)
        self.assertEqual(self.c.post(f'/api/projects/{self.pid}/analyze/matte', json={'layerId': 'gone'}).status_code, 400)

    def run_matte(self, change_during_run=False):
        source = matte_source(service.store.load(self.pid), 'shot')
        seen = []
        def run(name, inputs, out_dir, progress=None):
            out_dir.mkdir(parents=True, exist_ok=True)
            n = ffprobe_frames(Path(inputs['video']))
            first = extract_frame(Path(inputs['video']), 0, out_dir/'source.png')
            seen.append(Image.open(first).convert('RGB').getpixel((10, 10)))
            frames = []
            for i in range(n):
                path = out_dir/f'fg_{i}.png'; im = Image.open(first).convert('RGBA'); im.save(path); frames.append(path)
            tr = out_dir/'tracks.json'; tr.write_text(json.dumps(dict(fps=24, frames=n, tracks=[])))
            if change_during_run:
                service.store.update(self.pid, lambda p: p.layers[0].update(assetId='changed'))
            return RunResult(name=name, job_id='local', status='success', outputs={'fg_png': frames, 'tracks_json': [tr]}, timing={})
        with patch.object(pipeline.runner, 'run', side_effect=run), patch.object(pipeline, 'stage_to_comfy_input', side_effect=lambda path, *a: str(path)), patch.object(pipeline, 'encode_matte_proxy'):
            result = pipeline.analyze_matte(service.store, self.pid, Ctx(), source=source)
        return result, source, seen

    def test_image_layer_stages_one_native_frame_and_preserves_composition(self):
        before = service.store.load(self.pid).layers
        result, source, seen = self.run_matte()
        self.assertEqual(result['frames'], 1)
        self.assertGreater(seen[0][0], 200); self.assertLess(seen[0][1], 60)
        p = service.store.load(self.pid)
        self.assertIsNone(p.media.video)
        self.assertEqual(p.layers, before)
        self.assertEqual(p.analysis.matteSource, source)
        with Image.open(service.store.project_dir(self.pid)/p.analysis.matte/'fg_00001.png') as im:
            self.assertEqual(im.size, (80, 48))

    def test_video_layer_uses_its_trim_instead_of_original_footage(self):
        path = service.store.project_dir(self.pid)/'media/two-colors.mp4'
        ffmpeg(['-f', 'lavfi', '-i', 'color=c=blue:s=80x48:r=24:d=0.5', '-f', 'lavfi', '-i', 'color=c=red:s=80x48:r=24:d=0.5', '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path])
        def setup(p):
            p.assets[0].update(kind='video', path='media/two-colors.mp4', duration=1)
            p.layers[0].update({'in': .5, 'out': 1})
        service.store.update(self.pid, setup)
        result, source, seen = self.run_matte()
        self.assertEqual(result['frames'], 12)
        self.assertEqual(source['in'], .5)
        self.assertGreater(seen[0][0], 200); self.assertLess(seen[0][2], 50)

    def test_completed_old_take_cannot_overwrite_current_matte(self):
        with self.assertRaisesRegex(ValueError, 'asset|source'):
            self.run_matte(change_during_run=True)
        self.assertIsNone(service.store.load(self.pid).analysis.matte)

    def test_stale_editor_save_preserves_provenance_with_output_bundle(self):
        result, source, _ = self.run_matte()
        r = self.c.put(f'/api/projects/{self.pid}', json=self.p)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['analysis']['matteSource'], source)
        self.assertEqual(r.json()['analysis']['occupancy'], result['occupancy'])


if __name__ == '__main__': unittest.main()


class PerClipMatteTests(LayerMatteTests):
    def test_each_clip_keeps_its_own_run_and_saves_keep_them(self):
        result, source, _ = self.run_matte()
        p = service.store.load(self.pid)
        self.assertEqual(p.analysis.mattes['shot']['matte'], result['matte'])
        self.assertEqual(p.analysis.mattes['shot']['matteSource'], source)
        self.assertEqual(p.analysis.mattes['shot']['tracks'], result['tracks'])
        # A stale editor save (no mattes, no matte) keeps the server's per-clip runs; a removed clip drops its run.
        body = self.c.get(f'/api/projects/{self.pid}').json()
        body['analysis'] = {**body['analysis'], 'mattes': {}, 'matte': None, 'matteSource': None}
        r = self.c.put(f'/api/projects/{self.pid}', json=body); r.raise_for_status()
        self.assertEqual(r.json()['analysis']['mattes']['shot']['matte'], result['matte'])
        body = r.json(); body['layers'] = []
        r = self.c.put(f'/api/projects/{self.pid}', json=body); r.raise_for_status()
        self.assertEqual(r.json()['analysis']['mattes'], {})
