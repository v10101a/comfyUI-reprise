#!/usr/bin/env python3
"""Copy the bundled offline example into a real local project that can be exported."""
from pathlib import Path
import json
import shutil
import urllib.request

root=Path(__file__).resolve().parents[1]
source=root/'apps/web/public/sample'
api='http://127.0.0.1:8787'
def request(path, body, method):
    req=urllib.request.Request(api+path,json.dumps(body).encode(),{'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
p=request('/api/projects',{'name':'Typeset — typography demo'},'POST')
project=json.loads((source/'project.json').read_text())
project.update(id=p['id'],name=p['name'])
# No generated shot is bundled. Keep this word visible as a regular caption.
for word in project['words']:
    if word['placement']=='inworld':
        word['placement']='overlay';word.pop('shotId',None)
project['shots']=[]
dest=root/'data/projects'/p['id']
for target,origin in [('media/sample.mp4','sample.mp4'),('media/sample.wav','sample.wav'),('analysis/words.json','words.json'),('analysis/tracks.json','tracks.json'),('analysis/matte/fg.webm','matte/fg.webm')]:
    out=dest/target;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/origin,out)
request('/api/projects/'+p['id'],project,'PUT')
print(p['id'])
print('Select Typeset — typography demo in Media → Projects, then Export.')
