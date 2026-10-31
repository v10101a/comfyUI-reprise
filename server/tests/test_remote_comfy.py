"""Remote transport isolation/preflight checks; no remote server required."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import httpx

from app.comfy import ComfyRunner, WorkflowRunError, WorkflowInputError, coerce, runner, generation_runner

class RemoteTransportTests(unittest.TestCase):
    def remote(self):
        return ComfyRunner(base_url='http://127.0.0.1:8190', comfyui_url='http://remote:8188', remote=True)

    def test_remote_paths_do_not_require_local_files(self):
        self.assertEqual(coerce('comfy_input_path','typeset/p/nonlocal.png','image',remote=True),'typeset/p/nonlocal.png')
        for value in ['../outside.png','/absolute.png','C:\\outside.png']:
            with self.assertRaises(WorkflowInputError):coerce('comfy_input_path',value,'image',remote=True)

    def test_remote_output_never_reads_local_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            called=[]
            output=SimpleNamespace(name='same.png',id='ignored',to_file=lambda dest:(called.append(dest),Path(dest).write_bytes(b'remote')))
            with patch('app.comfy.decode_asset_id',return_value={'filename':'same.png'}),patch('app.comfy.local_output_path',side_effect=AssertionError('Must not use local disk')):
                p=self.remote()._fetch_output(output,Path(tmp))
            self.assertEqual(p.read_bytes(),b'remote')
            self.assertEqual(len(called),1)

    def test_sdk_clients_restore_environment(self):
        previous=os.environ.get('COMFY_BASE_URL')
        urls=[]
        with patch('comfy_sdk.Comfy',side_effect=lambda **kw:urls.append(os.environ['COMFY_BASE_URL']) or object()):
            ComfyRunner(base_url='http://local:8189').client()
            self.remote().client()
        self.assertEqual(urls,['http://local:8189','http://127.0.0.1:8190'])
        self.assertEqual(os.environ.get('COMFY_BASE_URL'),previous)

    def test_missing_nodes_weights_and_wrong_proxy_fail_before_submit(self):
        def response(data):return httpx.Response(200,json=data,request=httpx.Request('GET','http://test'))
        graph={'1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':'missing.safetensors'}},'2':{'class_type':'VHS_VideoCombine','inputs':{}}}
        registry={'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['other.safetensors']]}}}}
        with patch('app.comfy.httpx.get',side_effect=[response({'upstream':'http://remote:8188'}),response(registry)]):
            with self.assertRaisesRegex(WorkflowRunError,'missing.safetensors.*VHS_VideoCombine'):
                self.remote().preflight_graph(graph)
        with patch('app.comfy.httpx.get',return_value=response({'upstream':'http://local:8188'})):
            with self.assertRaisesRegex(WorkflowRunError,'Remote proxy upstream'):
                self.remote().preflight_graph(graph)

    def test_upload_uses_returned_remote_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'plate.png';image.write_bytes(b'png')
            response=httpx.Response(200,json={'name':'plate_1.png','subfolder':'typeset/p/s','type':'input'},request=httpx.Request('POST','http://remote:8188/upload/image'))
            with patch('app.comfy.httpx.post',return_value=response) as post:
                result=self.remote().stage_image(image,'p','s','plate.png')
            self.assertEqual(result,'typeset/p/s/plate_1.png')
            self.assertEqual(post.call_args.args[0],'http://remote:8188/upload/image')
            self.assertEqual(post.call_args.kwargs['data']['overwrite'],'false')

if __name__=='__main__':unittest.main()
