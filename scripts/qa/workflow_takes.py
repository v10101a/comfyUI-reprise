"""Comfy smoke check: reference input -> two outputs, tagged to a layer without applying them.
Uses a temporary project store and ImageInvert; optional --remote URL checks remote upload/SDK/download.
"""
import argparse,io,json,os,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server'))
parser=argparse.ArgumentParser();parser.add_argument('--remote');args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='typeset-takes-') as tmp:
    os.environ.update(TYPESET_DATA_DIR=tmp,TYPESET_COMFY_MODE='sdk' if args.remote else 'direct',TYPESET_REMOTE_COMFY_URL=args.remote or '')
    from fastapi.testclient import TestClient
    from PIL import Image
    from app.main import app
    from app.models import Project
    graph={
      '1':dict(class_type='LoadImage',inputs=dict(image='reference.png')),
      '2':dict(class_type='ImageInvert',inputs=dict(image=['1',0])),
      '3':dict(class_type='SaveImage',inputs=dict(images=['2',0],filename_prefix='typeset/qa/takes'))}
    with TestClient(app) as c:
        p=c.post('/api/projects',json=dict(name='Isolated workflow check')).json();pid=p['id']
        png=io.BytesIO();Image.new('RGB',(64,64),(230,30,50)).save(png,format='PNG')
        r=c.post(f'/api/projects/{pid}/assets',files={'file':('reference.png',png.getvalue(),'image/png')});r.raise_for_status();a=r.json()
        p=c.get(f'/api/projects/{pid}').json()
        layer=dict(id='visual',kind='media',assetId=a['id'],name='Motion',start=1,**{'in':0},out=3,transform=dict(x=.2,scale=.8),opacity=.7,
                   generation=dict(workflowId='pending',workflows={'pending':dict(inputs={},sources={'media':a['id']},variants=2)}))
        p['layers']=[layer];r=c.put(f'/api/projects/{pid}',json=p);r.raise_for_status()
        # The server retains the new generation/takes fields through its Pydantic model.
        assert Project.model_validate(r.json()).model_dump()['layers'][0]['generation']==layer['generation']
        r=c.post('/api/workflows',json=dict(name='Reference invert smoke check',graph=graph));r.raise_for_status();wf=r.json()
        r=c.post(f"/api/projects/{pid}/workflows/{wf['id']}/run",json=dict(layerId='visual',variants=2,remote=bool(args.remote),sources={'media':{'assetId':a['id']}}));r.raise_for_status();job=r.json()
        deadline=time.monotonic()+90
        while job['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(.5);job=c.get(f"/api/jobs/{job['id']}").json()
        assert job['status']=='done',job
        assets=job['result']['assets'];assert len(assets)==2
        assert all(x['source']['layerId']=='visual' and x['source']['remote']==bool(args.remote) for x in assets)
        assert all(x['source']['from']['media']['assetId']==a['id'] for x in assets)
        after=c.get(f'/api/projects/{pid}').json();assert after['layers']==[layer]
        assert len(after['assets'])==3
        output=Image.open(Path(tmp)/'projects'/pid/assets[0]['path']).convert('RGB').getpixel((0,0))
        assert all(abs(x-y)<=1 for x,y in zip(output,(25,225,205))),output
        report=dict(status=job['status'],variants=len(assets),layerUnchanged=True,referenceProvenance=True,outputPixel=output,remote=bool(args.remote))
        out=ROOT/'outputs/progress/takes'/('remote-workflow.json' if args.remote else 'local-workflow.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2));print(json.dumps(report))
