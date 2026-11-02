"""Reconcile moved song provenance paths in existing projects, preserving their edits."""
import json
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/songs/organization'
PAIRS = sorted(json.loads((OUT / 'moves.json').read_text()).items(), key=lambda p: -len(p[0]))
API = httpx.Client(base_url='http://127.0.0.1:8787', timeout=60)


def req(method, route, **kwargs):
    r = API.request(method, route, **kwargs); r.raise_for_status(); return r.json()


def updated(value):
    if isinstance(value, str):
        for old, new in PAIRS:
            value = value.replace(old, new)
        return value
    if isinstance(value, list): return [updated(x) for x in value]
    if isinstance(value, dict): return {k: updated(v) for k, v in value.items()}
    return value


def main():
    result = []
    for pid in ['c82161a0-7774-4add-b974-bcc92461397a', '48f2389d-1d2e-42ff-af86-f90b4d8c4600']:
        route = f'/api/projects/{pid}'
        for _ in range(5):
            current = req('GET', route); new = updated(current)
            if new == current: break
            for key in ['layers', 'words', 'media', 'duration']:
                assert current.get(key) == new.get(key), f'Unexpected edit: {key}'
            if req('GET', route) != current: continue
            backup = OUT / f'{pid}_before.json'
            if not backup.exists(): backup.write_text(json.dumps(current, indent=2))
            saved = req('PUT', route, json=new)
            for key in ['layers', 'words', 'media', 'duration']:
                assert saved.get(key) == current.get(key)
            result.append({'id': pid, 'editedOnlyProvenancePaths': True})
            break
        else:
            raise RuntimeError(f'Concurrent edits kept changing {pid}; no update applied')
    (OUT / 'project_updates.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
