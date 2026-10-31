"""Opt-in upload → Comfy SDK/separate proxy → remote graph → local download check.
No model required. Existing local proxy and application settings remain untouched.
"""
from pathlib import Path
import argparse
import json
import sys
import tempfile
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.comfy import ComfyRunner, WorkflowRunError
from PIL import Image

root=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser()
p.add_argument('--remote',default='http://100.104.17.103:8188')
p.add_argument('--proxy',default='http://127.0.0.1:8190')
a=p.parse_args()
r=ComfyRunner(base_url=a.proxy,comfyui_url=a.remote,remote=True)
out=root/'outputs/remote-sdk-smoke';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    temp=Path(temp)
    source=temp/'test.png';Image.new('RGB',(48,32),(18,220,91)).save(source)
    graph=json.loads((root/'docs/workflows/smoke_test_api.json').read_text())
    graph['3']['inputs']['filename_prefix']='typeset/sdk_smoke/test'
    (temp/'smoke.api.json').write_text(json.dumps(graph))
    (temp/'smoke.inputs.json').write_text(json.dumps({'workflow':'smoke.api.json','inputs':{'image':{'node':'1','field':'image','kind':'comfy_input_path'}},'outputs':{'image':{'node':'3','type':'image'}}}))
    r.preflight('smoke',temp)
    uploaded=r.stage_image(source,'transport-'+uuid.uuid4().hex,'test.png')
    result=r.run('smoke',{'image':uploaded},out,workflows_dir=temp,timeout=120)
    image=Image.open(result.first('image'))
    assert image.size==(256,256),image.size
    assert image.convert('RGB').getpixel((128,128))==(18,220,91)
    report={'remote':a.remote,'proxy':a.proxy,'job_id':result.job_id,'uploaded':uploaded,'outputs':{k:[str(v) for v in values] for k,values in result.outputs.items()},'timing':result.timing,'local_default_unchanged':True}
    try:r.preflight('ltx_i2v')
    except WorkflowRunError as exc:report['ltx_readiness']=str(exc)
    else:report['ltx_readiness']='ready'
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
r.reset_client()
