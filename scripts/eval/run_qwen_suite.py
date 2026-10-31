#!/usr/bin/env python3
"""Qwen-Image-Edit-2511 INT8/Lightning evaluation on an identical blank-wall input.

Uses the shared recorder. This is image editing, so comparison to pure text-to-image
models is qualitative; every physical-word case receives the same source wall image.
Run only after all files in download_qwen.sh finish downloading.
"""
import argparse
import json
import os
import subprocess
import re
import urllib.request
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = Path.home() / 'ComfyUI/models'
REQUIRED = [
    'diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors',
    'text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors',
    'vae/qwen_image_vae.safetensors',
    'loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors',
]
LOG = ROOT/'docs/eval/current-results.jsonl'
COMFY_HTTP = os.environ.get('COMFY_HTTP', 'http://127.0.0.1:8188').rstrip('/')

def records():
    return [json.loads(s) for s in LOG.read_text().splitlines() if s.strip()] if LOG.exists() else []

def contact_sheet():
    """Unretouched, labeled inspection grid; unavailable cases are not invented."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    items=[]
    for ident in ['edit_wall','neon','louder','stay','holdon','forever','echo']:
        rows=[r for r in records() if r.get('tag')=='qwen_'+ident and r.get('status')=='success']
        if not rows: continue
        candidates=[Path(p) for p in rows[-1].get('outputs',[]) if p.lower().endswith('.png')]
        if candidates and candidates[0].exists(): items.append((ident,candidates[0]))
    if not items: return
    items.insert(0,('same wall input',ROOT/'docs/eval/plates/wall_1024x576.png'))
    width,height,columns=384,260,min(4,len(items))
    sheet=Image.new('RGB',(columns*width,((len(items)+columns-1)//columns)*height),'#17191b')
    draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype(str(ROOT/'apps/web/public/fonts/SpaceMono-Regular.ttf'),15)
    for index,(label,path) in enumerate(items):
        x,y=index%columns*width,index//columns*height
        with Image.open(path) as im:
            tile=ImageOps.contain(im.convert('RGB'),(width-12,height-40))
            sheet.paste(tile,(x+(width-tile.width)//2,y+32+(height-40-tile.height)//2))
        draw.text((x+8,y+8),label,font=font,fill='#e4e9de')
    output=ROOT/'docs/eval/contact-sheets/qwen_edit.jpg';output.parent.mkdir(parents=True,exist_ok=True)
    sheet.save(output,quality=92)
    print('Contact sheet:',output,flush=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--case', default='all', help='all, edit_wall, or physical-word id')
    ap.add_argument('--timeout', type=int, default=900)
    args=ap.parse_args()
    missing=[name for name in REQUIRED if not (MODEL_ROOT/name).is_file()]
    if missing: raise SystemExit('Missing completed downloads: '+', '.join(missing))
    prompts=json.loads((ROOT/'scripts/eval/prompts_text.json').read_text())
    cases=[{'id':'edit_wall','prompt':'Add the exact word NEON as a realistic pink neon sign mounted on the brick wall. Preserve the wall and composition.'}]+prompts
    for case in cases:
        if args.case not in ('all',case['id']): continue
        tag='qwen_'+case['id']
        existing=[r for r in records() if r.get('tag')==tag and r.get('status')=='success']
        if existing:
            print(tag,'already passed; preserving existing result',flush=True)
            continue
        print('Starting',tag,flush=True)
        before_count = len(records())
        started = time.time()
        command=[sys.executable,'-u',str(ROOT/'scripts/eval/comfy_run.py'),
            str(ROOT/'workflows/eval/qwen2511_int8_edit.api.json'),
            '--tag',tag,'--set','6.prompt='+case['prompt'],
            '--seed','104','--seed-node','11','--out',str(ROOT/'docs/eval/current'),
            '--log',str(LOG),'--timeout',str(args.timeout)]
        # Preserve the submitted prompt ID immediately, so an interrupted coordinator
        # can recover the job from ComfyUI history rather than submit it again.
        output_dir=ROOT/'docs/eval/current'/tag
        output_dir.mkdir(parents=True,exist_ok=True)
        chunks=[]
        with (output_dir/'runner.log').open('a',buffering=1) as logfile:
            logfile.write(json.dumps({'started':time.strftime('%Y-%m-%d %H:%M:%S'),'comfy_http':COMFY_HTTP,'command':command})+'\n')
            result=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            for line in result.stdout:
                chunks.append(line);logfile.write(line);print(line,end='',flush=True)
            result.wait()
        runner_output=''.join(chunks)
        if result.returncode:
            current = [r for r in records()[before_count:] if r.get('tag') == tag]
            # The shared recorder writes execution errors, but not transport/timeouts.
            if not current:
                match = re.search(r'submitted ([0-9a-f-]{36})', runner_output)
                prompt_id = match.group(1) if match else None
                if prompt_id:
                    # Both routes target this exact job; never interrupt another worker.
                    for path, body in [('/queue', {'delete':[prompt_id]}), ('/interrupt', {'prompt_id':prompt_id})]:
                        req=urllib.request.Request(COMFY_HTTP+path, data=json.dumps(body).encode(), headers={'content-type':'application/json'}, method='POST')
                        try:
                            with urllib.request.urlopen(req, timeout=10): pass
                        except Exception as exc: print('Targeted cleanup failed:',exc,file=sys.stderr)
                failure={'tag':tag, 'workflow':'workflows/eval/qwen2511_int8_edit.api.json', 'status':'runner_error', 'error':{'exception_message':runner_output[-4000:]}, 'wall_s':round(time.time()-started,2), 'outputs':[], 'seed':104, 'prompt_id':prompt_id, 'time':time.strftime('%Y-%m-%d %H:%M:%S')}
                with LOG.open('a') as f:f.write(json.dumps(failure)+'\n')
            print(f'Stopping Qwen suite after {tag} failed (exit {result.returncode}); inspect ComfyUI and recorded error.',flush=True)
            contact_sheet()
            return result.returncode
        contact_sheet()
    return 0

if __name__=='__main__':sys.exit(main())
