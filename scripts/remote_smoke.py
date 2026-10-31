#!/usr/bin/env python3
"""Verify remote upload, execution and download using a synthetic image."""
import argparse
import json
import time
import uuid
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument('url')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
with httpx.Client(base_url=args.url.rstrip('/'), timeout=60) as client:
    src = root / 'docs/eval/plates/wall_768x448.png'
    with src.open('rb') as file:
        response = client.post('/upload/image', data={'type': 'input', 'subfolder': 'typeset/smoke'},
                               files={'image': (uuid.uuid4().hex + '.png', file, 'image/png')})
    response.raise_for_status()
    upload = response.json()
    workflow = json.loads((root / 'docs/workflows/smoke_test_api.json').read_text())
    for node in workflow.values():
        if node['class_type'] == 'LoadImage':
            node['inputs']['image'] = '/'.join(filter(None, [upload.get('subfolder', ''), upload['name']]))
    response = client.post('/prompt', json={'prompt': workflow, 'client_id': str(uuid.uuid4())})
    response.raise_for_status()
    prompt_id = response.json()['prompt_id']
    started = time.monotonic()
    while time.monotonic() - started < 120:
        response = client.get('/history/' + prompt_id)
        response.raise_for_status()
        history = response.json().get(prompt_id)
        if history:
            break
        time.sleep(.5)
    else:
        raise TimeoutError('Remote smoke did not finish within 120 seconds')
    if history['status']['status_str'] != 'success':
        raise RuntimeError(history['status'])
    destination = root / 'outputs/remote-smoke'
    destination.mkdir(parents=True, exist_ok=True)
    for node in history['outputs'].values():
        for item in node.get('images', []):
            response = client.get('/view', params={k: item[k] for k in ('filename', 'subfolder', 'type') if k in item})
            response.raise_for_status()
            (destination / Path(item['filename']).name).write_bytes(response.content)
    result = {'server': args.url, 'prompt_id': prompt_id,
              'elapsed_seconds': round(time.monotonic() - started, 2), 'status': 'success',
              'outputs': str(destination)}
    (root / 'docs/eval/remote-smoke.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
