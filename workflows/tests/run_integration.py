"""Exercise real sidecars through the same SDK runner used by the server.
Run from repo root: server/.venv/bin/python workflows/tests/run_integration.py words
"""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server'))
from app.comfy import runner
parser=argparse.ArgumentParser()
parser.add_argument('name',choices=['words','matte','text_plate','ltx_i2v','ltx_morph'])
args=parser.parse_args()
inputs={
'words':{'audio':'typeset/test/words-test.wav','lyrics':'Words belong in the world.\nNeon light, chrome dreams.','language':'en'},
'matte':{'video':'typeset/test/person_short.mp4','fps':24},
'text_plate':{'frame':'eval/wall_768x448.png','text':'NEON','prompt':'pink neon'},
'ltx_i2v':{'image':'eval/neon_768x448.png','prompt':'A neon sign glows gently, static camera, readable lettering','length':25,'width':512,'height':320,'seed':8642},
'ltx_morph':{'first':'eval/neon_768x448.png','last':'eval/chrome_768x448.png','prompt':'Neon letters slowly become polished silver','length':25,'width':512,'height':320,'seed':8642},
}[args.name]
last_status = None
def progress(status, elapsed):
    global last_status
    if status != last_status:
        print(status, round(elapsed, 1), flush=True)
        last_status = status
result=runner.run(args.name,inputs,Path('outputs/integration')/args.name,progress=progress,timeout=600)
if args.name == 'words':
    words = json.loads(result.first('words_json').read_text())['words']
    assert [w['text'] for w in words] == ['Words','belong','in','the','world.','Neon','light,','chrome','dreams.']
    assert all(w['end'] > w['start'] for w in words)
    assert all(a['end'] <= b['start'] for a,b in zip(words, words[1:]))
elif args.name == 'matte':
    from PIL import Image
    tracks = json.loads(result.first('tracks_json').read_text())
    assert tracks['frames'] == len(result.outputs['fg_png']) == 12
    assert tracks['fps'] == 24
    assert len(tracks['tracks'][0]['frames']) == 12
    im = Image.open(result.outputs['fg_png'][0])
    assert im.mode == 'RGBA' and im.size == (512, 320)
    assert im.getchannel('A').getextrema() == (0, 255)
elif args.name in ('ltx_i2v', 'ltx_morph'):
    import subprocess
    probe = json.loads(subprocess.check_output(['/opt/homebrew/bin/ffprobe','-v','error','-show_entries','stream=width,height,nb_frames','-of','json',str(result.first('video'))]))
    stream = probe['streams'][0]
    assert (stream['width'],stream['height'],int(stream['nb_frames'])) == (512,320,25)
doc={'name':args.name,'job_id':result.job_id,'status':result.status,'timing':result.timing,'outputs':{k:[str(p) for p in v] for k,v in result.outputs.items()}}
print(json.dumps(doc,indent=2))
Path('outputs/integration').mkdir(exist_ok=True,parents=True)
Path(f'outputs/integration/{args.name}-result.json').write_text(json.dumps(doc,indent=2)+'\n')
