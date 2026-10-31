#!/usr/bin/env python3
"""Sequential, repeatable installed-model comparison. No downloads or cloud APIs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

p = argparse.ArgumentParser()
p.add_argument('--group', choices=['video','image','all'], default='all')
p.add_argument('--resume', action='store_true', help='Skip successful cases whose artifacts still exist')
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
runner = root / 'scripts/eval/comfy_run.py'

def run(name, graph, args):
    log = root / 'docs/eval/current-results.jsonl'
    if a.resume and log.exists():
        for line in log.read_text().splitlines():
            record = json.loads(line)
            if record.get('tag') == name and record.get('status') == 'success' and record.get('outputs') and all((root / path).is_file() for path in record['outputs']):
                print('SKIP completed ' + name, flush=True)
                return
    print('\nRUN ' + name, flush=True)
    cmd = [sys.executable, '-u', str(runner), 'workflows/eval/'+graph+'.api.json', '--tag', name, '--out', 'docs/eval/current', '--log', 'docs/eval/current-results.jsonl', '--timeout', '900', *args]
    result = subprocess.run(cmd, cwd=root)
    if result.returncode:
        with (root/'docs/eval/suite-failures.jsonl').open('a') as f:
            f.write(json.dumps({'tag':name, 'command':cmd, 'returncode':result.returncode})+'\n')
    if result.returncode == 1:
        # A timed-out GPU job can still be active. Do not pile more work on top.
        print('Stopped after submission failure or timeout. Inspect server before resuming.', flush=True)
        sys.exit(1)

if a.group in ('video','all'):
    for tag, graph in [('i2v_letters','ltx_i2v'), ('morph_letters','ltx_morph'), ('spatial_upscale','ltx_t2v_upscale2x'), ('ltx13b_gguf','ltx13b_gguf_t2v')]:
        run(tag, graph, ['--seed','104','--seed-node','10','--frames','5'])
if a.group in ('image','all'):
    prompts=json.loads((root/'scripts/eval/prompts_text.json').read_text())
    for model,node in [('klein4b_t2i','10'),('zimage_t2i','8')]:
        for item in prompts:
            run(model+'_'+item['id'], model, ['--set','4.text='+item['prompt'],'--seed','104','--seed-node',node])
    run('klein4b_edit_wall','klein4b_edit',['--set','4.text=Add the exact word NEON as a realistic pink neon sign mounted on the brick wall. Preserve the wall and composition.','--seed','104','--seed-node','10'])
