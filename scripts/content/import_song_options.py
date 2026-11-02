"""Add prepared song options and linked board cards without replacing timeline clips."""
import argparse
import copy
import json
import math
import mimetypes
import shutil
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = {'playboi': 'c82161a0-7774-4add-b974-bcc92461397a',
            'so-i-die': '48f2389d-1d2e-42ff-af86-f90b4d8c4600'}
API = httpx.Client(base_url='http://127.0.0.1:8787', timeout=120)


def req(method, path, **kwargs):
    r = API.request(method, path, **kwargs); r.raise_for_status(); return r.json()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('manifest', type=Path); args = parser.parse_args()
    config = json.loads(args.manifest.read_text()); slug = config['song']; pid = PROJECTS[slug]
    route = f'/api/projects/{pid}'; pdir = ROOT / 'data/projects' / pid
    log = args.manifest.with_suffix('.import.json')
    imported = json.loads(log.read_text()) if log.exists() else {}
    for item in config['items']:
        if item['name'] in imported: continue
        path = ROOT / item['file']
        with path.open('rb') as f:
            a = req('POST', route + '/assets', files={'file': (path.name, f, mimetypes.guess_type(path.name)[0] or 'application/octet-stream')},
                    data={'name': item['title'], 'addLayer': 'false'})
        imported[item['name']] = a['id']; log.write_text(json.dumps(imported, indent=2))
    for _ in range(5):
        current = req('GET', route); p = copy.deepcopy(current)
        cards = p.setdefault('board', {}).setdefault('cards', [])
        gid = config['id']; group = next((c for c in cards if c['id'] == gid), None)
        y = group['y'] if group else max(c.get('y', 0) + c.get('h', 0) for c in cards) + 60
        columns = config.get('columns', 2)
        if not group: cards.append({'id': gid, 'kind': 'group', 'title': config['title'], 'x': 0, 'y': y,
                                    'w': columns * 490 + 50, 'h': 70 + math.ceil(len(config['items']) / columns) * 310, 'role': 'motion'})
        for i, item in enumerate(config['items']):
            aid = imported[item['name']]; a = next(a for a in p['assets'] if a['id'] == aid)
            run = json.loads((ROOT / item['run']).read_text())
            source = {'kind': 'workflow', 'layerId': item['layer'], 'workflowName': run['engine'],
                      'recipe': run, 'seed': run.get('seed'), 'promptId': run.get('prompt_id'),
                      'importedFrom': item['file'], 'songOptionBatch': gid}
            if item.get('prepared'):
                folder = ROOT / item['prepared']; rel = f"audio/{item['name']}"
                dest = pdir / rel; dest.mkdir(parents=True, exist_ok=True)
                for old, new in [('gen.wav', 'drive.wav'), ('mux.wav', 'song.wav')]:
                    shutil.copy2(folder / old, dest / new)
                ref = next((a for a in p['assets'] if a.get('source', {}).get('importedFrom') == run['source_image']), None)
                source.update(workflowId='ed3fbc575706', remote=True,
                              postprocess={'timeScale': run['stretch'], 'trimStart': run['pre'], 'fps': 24, 'audio': rel + '/song.wav'},
                              inputs={k: run[k] for k in ('prompt', 'seed', 'length')},
                              fromPreparedAudio=rel + '/drive.wav')
                source['inputs'].update(width=run['size'][0], height=run['size'][1])
                source['regeneration'] = {'inputs': source['inputs'], 'sources': {'image': ref['id'] if ref else '', 'audio': '@prepared'},
                                          'mediaFiles': {'audio': {'path': rel + '/drive.wav', 'name': item['title'] + ' · vocal'}},
                                          'postprocess': source['postprocess'], 'variants': 1}
            a['source'] = source
            cid = 'card-' + item['name']
            if not any(c['id'] == cid for c in cards):
                cards.append({'id': cid, 'kind': 'asset', 'title': item['title'], 'assetId': aid, 'layerId': item['layer'],
                              'x': 24 + (i % columns) * 490, 'y': y + 70 + (i // columns) * 310,
                              'w': 466, 'h': 275, 'role': 'reference' if a['kind'] == 'image' else 'motion'})
        if req('GET', route) != current: continue
        args.manifest.with_suffix('.before.json').write_text(json.dumps(current, indent=2))
        saved = req('PUT', route, json=p)
        assert saved['layers'] == current['layers'] and saved['media'] == current['media'] and saved['words'] == current['words']
        print(json.dumps({'project': pid, 'assets': imported, 'timelinePreserved': True}, indent=2)); return
    raise RuntimeError('Concurrent project edits prevented a safe merge; uploads retained')


if __name__ == '__main__': main()
