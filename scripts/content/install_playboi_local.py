"""Add the local-v8 Playboi stills + LTX clips to the Playboi shot studio as new scenes (takes + refs + board cards).
Never touches existing layers, media, words or the current cut; registers a local LTX i2v workflow once so the
scenes can be regenerated from Studio on the Mac.

  python3 scripts/content/install_playboi_local.py outputs/songs/playboi/local_v8 [--only a b]
"""
import argparse, copy, json, math, mimetypes, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]
PID = 'c82161a0-7774-4add-b974-bcc92461397a'
API = httpx.Client(base_url='http://127.0.0.1:8787', timeout=180)
sys.path.insert(0, str(ROOT / 'scripts/content'))


def req(m, p, **kw):
    r = API.request(m, p, **kw); r.raise_for_status(); return r.json()


def workflow(state):
    if state.get('workflow'): return state['workflow']
    from local_playboi_motion import graph
    g = graph('direction', 'placeholder.png', 7, 1344, 768, 49, 24, 'typeset/studio/pb_local_ltx')
    g['20'].setdefault('_meta', {})['title'] = 'Scene reference'; g['3'].setdefault('_meta', {})['title'] = 'Direction'
    g['10'].setdefault('_meta', {})['title'] = 'Variation seed'
    w = req('POST', '/api/workflows', json={'name': 'Scene motion · LTX local', 'graph': g})
    w = req('PUT', f"/api/workflows/{w['id']}", json={'inputs': {'image': {'node': '20', 'field': 'image'}, 'prompt': {'node': '3', 'field': 'text'},
            'seed': {'node': '10', 'field': 'noise_seed'}, 'length': {'node': '22', 'field': 'length'}}, 'output': {'node': '12', 'type': 'video'}})
    state['workflow'] = w['id']; return w['id']


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('dir', type=Path); ap.add_argument('--only', nargs='*'); a = ap.parse_args()
    d = a.dir; cfg = json.loads((d / 'jobs.json').read_text()); motion = json.loads((d / 'motion.json').read_text()) if (d / 'motion.json').exists() else {'shots': []}
    log = d / 'install.json'; state = json.loads(log.read_text()) if log.exists() else {'assets': {}}
    wid = workflow(state); log.write_text(json.dumps(state, indent=2))
    route = f'/api/projects/{PID}'

    def upload(path: Path, title: str, source: dict):
        key = str(path.relative_to(ROOT))
        if key in state['assets']: return state['assets'][key]
        with path.open('rb') as f:
            asset = req('POST', route + '/assets', files={'file': (path.name, f, mimetypes.guess_type(path.name)[0] or 'application/octet-stream')},
                        data={'name': title, 'addLayer': 'false'})
        state['assets'][key] = asset['id']; log.write_text(json.dumps(state, indent=2)); return asset['id']

    picks = json.loads((d / 'picks.json').read_text()) if (d / 'picks.json').exists() else {}
    shots = [s for s in cfg['shots'] if not a.only or s['name'] in a.only]
    plan = []
    for s in shots:
        stills = sorted((d / 'raw' / s['name']).glob('*.png'))
        if s['name'] in picks: stills = [d / 'raw' / s['name'] / p for p in picks[s['name']]]
        clips = [(m, sorted((d / 'clips' / m['name']).glob('*.mp4'))) for m in motion['shots'] if m.get('still') == s['name']]
        if not stills: continue
        refs = [(p, upload(p, f"{s['name']} · still {p.stem.split('_')[-1]}", {})) for p in stills]
        takes = []
        for m, files in clips:
            for f in files:
                takes.append((m, f, upload(f, f"{s['name']} · LTX {m['name'].split('_')[-1]}", {})))
        plan.append((s, refs, takes))

    for _ in range(5):
        current = req('GET', route); p = copy.deepcopy(current)
        cards = p['board']['cards']; scenes = p['board'].setdefault('scenes', [])
        y0 = max(c.get('y', 0) + c.get('h', 0) for c in cards) + 60
        sy = max(s['y'] for s in scenes) + 490 if scenes else 0
        for i, (s, refs, takes) in enumerate(plan):
            sid = 'pb-local-' + s['name']
            if any(x['id'] == sid for x in scenes): continue
            for key, aid in [*refs, *[(f, aid) for _, f, aid in takes]]:
                asset = next(x for x in p['assets'] if x['id'] == aid)
                rel = str(key.relative_to(ROOT)) if isinstance(key, Path) else key
                src = {'kind': 'workflow', 'importedFrom': rel, 'workflowName': 'LTX-Video 2B local' if rel.endswith('.mp4') else 'Qwen-Image-Edit-2511 local',
                       'recipe': {'prompt': cfg['identity'] + ' ' + s['prompt'], 'seed': s['seed'], 'face': cfg['face'], 'look': s.get('look', cfg['look'])}}
                if rel.endswith('.mp4'):
                    m = next(m for m, f, _ in takes if f == key); run = key.parent / 'run.json'
                    src['recipe'] = json.loads(run.read_text()) if run.exists() else {'prompt': m['prompt'], 'seed': m['seed']}
                asset['source'] = src
            roles = {aid: 'reference' for _, aid in refs}; roles.update({aid: 'motion' for _, _, aid in takes})
            first_ref = refs[0][1]
            gen = {'workflowId': wid, 'workflows': {wid: {'inputs': {'prompt': next((m['prompt'] for m, _, _ in takes), s['prompt']),
                   'seed': next((m['seed'] for m, _, _ in takes), s['seed']), 'length': 49}, 'sources': {'image': first_ref}, 'variants': 1}}}
            scenes.append({'id': sid, 'name': 'Local v8 · ' + s['name'].replace('_', ' '), 'x': 310 * (i % 2), 'y': sy + 490 * (i // 2),
                           'clips': [], 'takes': [aid for _, _, aid in takes], 'refs': [aid for _, aid in refs], 'roles': roles,
                           'notes': s['prompt'], 'generation': gen})
            items = [(aid, f"Still · {k.stem.split('_')[-1]}", 'reference') for k, aid in refs] + [(aid, f"LTX · {m['name']}", 'motion') for m, _, aid in takes]
            cols = 4; gy = y0 + i * (70 + math.ceil(len(items) / cols) * 310 + 40)
            cards.append({'id': 'group-' + sid, 'kind': 'group', 'title': f"Local v8 / {s['name'].replace('_', ' ')}", 'x': 0, 'y': gy,
                          'w': cols * 490 + 50, 'h': 70 + math.ceil(len(items) / cols) * 310, 'role': 'reference'})
            for j, (aid, title, role) in enumerate(items):
                cards.append({'id': f'card-{sid}-{aid}', 'kind': 'asset', 'title': title, 'assetId': aid, 'x': 24 + (j % cols) * 490,
                              'y': gy + 70 + (j // cols) * 310, 'w': 466, 'h': 275, 'role': role})
        if req('GET', route) != current: continue
        (d / 'project_before.json').write_text(json.dumps(current, indent=2))
        saved = req('PUT', route, json=p)
        assert saved['layers'] == current['layers'] and saved['media'] == current['media'] and saved['words'] == current['words']
        print(json.dumps({'project': PID, 'scenes': [s for s, _, _ in [(x['id'], 0, 0) for x in saved['board']['scenes'] if x['id'].startswith('pb-local-')]],
                          'assets': len(state['assets']), 'workflow': wid}), flush=True); return
    raise RuntimeError('concurrent edits; uploads retained, rerun')


if __name__ == '__main__': main()
