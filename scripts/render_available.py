#!/usr/bin/env python3
"""Krea images → local LTX or remote MiniMax video, without model downloads.

Run with server/.venv/bin/python. --plate reuses an existing image instead of
asking Krea for a new one. Outputs and exact submitted graphs are retained.
"""
import argparse
import json
import mimetypes
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def execute(base, graph, destination, timeout=900):
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'workflow.json').write_text(json.dumps(graph, indent=2) + '\n')
    with httpx.Client(base_url=base.rstrip('/'), timeout=60) as client:
        response = client.post('/prompt', json={'prompt': graph, 'client_id': str(uuid.uuid4())})
        if response.is_error:
            raise RuntimeError(f'{base} rejected the workflow ({response.status_code}): {response.text[:2000]}')
        response.raise_for_status()
        job = response.json()['prompt_id']
        (destination / 'submitted.json').write_text(json.dumps({'server': base, 'prompt_id': job}, indent=2) + '\n')
        print(f'Submitted {job} to {base}', flush=True)
        started = time.monotonic()
        history = None
        while time.monotonic() - started < timeout:
            response = client.get('/history/' + job)
            response.raise_for_status()
            history = response.json().get(job)
            if history:
                break
            time.sleep(.5)
        if not history:
            raise TimeoutError(f'Job {job} exceeded {timeout}s; check {base}/queue before retrying')
        (destination / 'history.json').write_text(json.dumps(history, indent=2) + '\n')
        if history['status']['status_str'] != 'success':
            errors = [payload.get('exception_message', kind)
                      for kind, payload in history['status'].get('messages', [])
                      if kind in ('execution_error', 'execution_interrupted')]
            raise RuntimeError(f'Job failed: {errors}; see {destination / "history.json"}')
        files = []
        for output in history.get('outputs', {}).values():
            for key in ('images', 'gifs', 'videos'):
                for item in output.get(key, []):
                    if item.get('type') != 'output':
                        continue
                    params = {k: item[k] for k in ('filename', 'subfolder', 'type') if k in item}
                    response = client.get('/view', params=params)
                    response.raise_for_status()
                    target = destination / Path(item['filename']).name
                    target.write_bytes(response.content)
                    files.append(target)
        if not files:
            raise RuntimeError(f'Job produced no downloadable output; see {destination / "history.json"}')
        print(f'Finished in {time.monotonic() - started:.1f}s: {files}', flush=True)
        return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gpu', default='http://100.104.17.103:8188')
    parser.add_argument('--mac', default='http://127.0.0.1:8188')
    parser.add_argument('--video-model', choices=('ltx', 'minimax'), default='ltx',
                        help='ltx runs on the Mac; minimax runs on the GPU host')
    parser.add_argument('--full-size', action='store_true',
                        help='MiniMax only: 1344×768, 124 frames (~5 seconds), instead of the short preview')
    parser.add_argument('--plate', type=Path, help='Reuse a still image; skip Krea generation')
    parser.add_argument('--image-prompt', default='A pink neon sign spelling exactly NEON on a rain-soaked brick wall at night, cinematic lighting.')
    parser.add_argument('--motion-prompt', help='Override the selected video workflow prompt')
    parser.add_argument('--seed', type=int, default=104)
    parser.add_argument('--out', type=Path, default=ROOT / 'outputs/available-models')
    args = parser.parse_args()
    if args.full_size and args.video_model != 'minimax':
        parser.error('--full-size requires --video-model minimax')
    run = args.out / uuid.uuid4().hex[:12]
    if args.plate:
        plate = args.plate.resolve()
        if not plate.is_file():
            raise FileNotFoundError(plate)
    else:
        graph = json.loads((ROOT / 'workflows/eval/krea2_remote_t2i.api.json').read_text())
        graph['4']['inputs']['text'] = args.image_prompt
        graph['7']['inputs']['seed'] = args.seed
        outputs = execute(args.gpu, graph, run / 'plate')
        plate = next(path for path in outputs if path.suffix.lower() == '.png')
    video_server = args.mac if args.video_model == 'ltx' else args.gpu
    with httpx.Client(base_url=video_server.rstrip('/'), timeout=60) as client, plate.open('rb') as file:
        response = client.post('/upload/image', data={'type': 'input', 'subfolder': 'typeset/available-models'},
                               files={'image': (run.name + plate.suffix.lower(), file,
                                                mimetypes.guess_type(plate.name)[0] or 'application/octet-stream')})
        response.raise_for_status()
        upload = response.json()
    if args.video_model == 'ltx':
        workflow = 'workflows/ltx_i2v.api.json'
        image_node, prompt_node, prompt_input, noise_node = '20', '3', 'text', '10'
    else:
        workflow = 'workflows/eval/minimax_remote_i2v.api.json'
        image_node, prompt_node, prompt_input, noise_node = '5', '6', 'prompt', '7'
    graph = json.loads((ROOT / workflow).read_text())
    graph[image_node]['inputs']['image'] = '/'.join(filter(None, [upload.get('subfolder', ''), upload['name']]))
    if args.motion_prompt is not None:
        graph[prompt_node]['inputs'][prompt_input] = args.motion_prompt
    elif args.video_model == 'ltx':
        graph[prompt_node]['inputs'][prompt_input] = 'A pink neon NEON sign on a brick wall, gentle camera push in and subtle changing light. The letters remain still and legible.'
    graph[noise_node]['inputs']['noise_seed'] = args.seed
    if args.full_size:
        graph['6']['inputs'].update(width=1344, height=768, length=124)
    outputs = execute(video_server, graph, run / 'video')
    manifest = {'plate': str(plate), 'outputs': [str(p) for p in outputs],
                'image_server': None if args.plate else args.gpu, 'video_server': video_server,
                'video_model': args.video_model,
                'models_downloaded': False}
    (run / 'result.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Run record:', run / 'result.json')


if __name__ == '__main__':
    main()
