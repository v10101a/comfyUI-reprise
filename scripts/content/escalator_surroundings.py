"""Keep the singing footage intact while revealing moving surroundings outside both performers.

Sampled masks form a conservative static protection area. This avoids the ghost person
that appears when a moving source's subject escapes the singing subject's silhouette.
"""
import hashlib
import json
import subprocess
import time
from pathlib import Path

import cv2
import httpx
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'outputs/songs/so-i-die'
OUT = BASE / 'motion'
OUT.mkdir(exist_ok=True)
MANIFEST = OUT / 'manifest.json'
STATE = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
API = httpx.Client(base_url='http://127.0.0.1:8787', timeout=120)


def req(method, path, **kwargs):
    r = API.request(method, path, **kwargs); r.raise_for_status(); return r.json()


def save(): MANIFEST.write_text(json.dumps(STATE, indent=2))


def ff(*args): subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], check=True)


def matte(key, src):
    entry = STATE.setdefault(key, {'source': str(src.relative_to(ROOT))})
    assert entry['source'] == str(src.relative_to(ROOT))
    if entry.get('matte'):
        cached = sorted((ROOT / entry['matte']).glob('fg_*.png'))
        if cached:
            return cached
    if key == 'down_singer' and not entry.get('id'):
        pid = '34d9f474-9ce6-48bb-80ba-e20b6fc26458'
        p = req('GET', f'/api/projects/{pid}')
        old = ROOT / 'data/projects' / pid / p['media']['video']['path']
        if hashlib.sha256(old.read_bytes()).digest() == hashlib.sha256(src.read_bytes()).digest():
            entry['id'] = pid; save()
    if not entry.get('id'):
        sample = OUT / f'{key}_sample.mp4'
        ff('-i', src, '-vf', 'fps=2', '-an', '-c:v', 'libx264', '-crf', '14', sample)
        p = req('POST', '/api/projects', json={'name': f'scratch · escalator mask / {key}'})
        entry['id'] = p['id']; save()
        with sample.open('rb') as f:
            req('POST', f"/api/projects/{p['id']}/media", files={'file': (sample.name, f, 'video/mp4')},
                data={'kind': 'video'})
    pid = entry['id']
    p = req('GET', f'/api/projects/{pid}')
    if not p['analysis'].get('matte'):
        if not entry.get('job'):
            entry['job'] = req('POST', f'/api/projects/{pid}/analyze/matte', json={})['id']; save()
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            j = req('GET', f"/api/jobs/{entry['job']}")
            if j['status'] == 'done': break
            if j['status'] in ('error', 'failed'): raise RuntimeError(j)
            print(key, j['status'], j.get('message', ''), flush=True)
            time.sleep(10)
        else: raise TimeoutError(key)
        p = req('GET', f'/api/projects/{pid}')
    path = ROOT / 'data/projects' / pid / p['analysis']['matte']
    masks = sorted(path.glob('fg_*.png'))
    assert masks, path
    entry['matte'] = str(path.relative_to(ROOT)); save()
    return masks


def main():
    for direction, take in [('up', 'sid_esc2_l7l8'), ('down', 'sid_esc_move_b')]:
        singer = BASE / 'singing' / take / f'{take}_mux.mp4'
        world = BASE / 'plates_bg' / f'bg_esc_{direction}' / f'bg_esc_{direction}_00001-audio.mp4'
        folder = OUT / direction; folder.mkdir(exist_ok=True)
        masks = matte(direction + '_singer', singer) + matte(direction + '_world', world)
        union = None
        for path in masks:
            with Image.open(path) as im: alpha = np.asarray(im.getchannel('A'))
            union = alpha.copy() if union is None else np.maximum(union, alpha)
        protect = cv2.dilate((union > 24).astype(np.uint8) * 255, np.ones((17, 17), np.uint8))
        protect = cv2.GaussianBlur(protect, (0, 0), 3)
        mask = folder / 'protect.png'; Image.fromarray(protect).save(mask)
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                             '-show_entries', 'stream=nb_frames', '-of', 'json', str(singer)]))
        frames = int(probe['streams'][0]['nb_frames'])
        dest = folder / f'sid_escalator_{direction}_singing.mp4'
        ff('-i', world, '-i', singer, '-loop', '1', '-framerate', '24', '-i', mask,
           '-filter_complex', '[0:v]format=gbrp,setpts=PTS-STARTPTS[w];[1:v]format=gbrp,setpts=PTS-STARTPTS[s];[2:v]format=gbrp[m];[w][s][m]maskedmerge,format=yuv420p[v]',
           '-map', '[v]', '-map', '1:a:0', '-frames:v', frames, '-c:v', 'libx264', '-preset', 'medium', '-crf', '16',
           '-c:a', 'copy', '-t', frames / 24, '-movflags', '+faststart', dest)
        recipe = json.loads((singer.parent / 'run.json').read_text())
        recipe.update(engine='wan2.2-s2v + moving surroundings', singing_source=str(singer.relative_to(ROOT)),
                      world_source=str(world.relative_to(ROOT)), protection=str(mask.relative_to(ROOT)),
                      composition='Keep original singer and nearby pixels; moving world only outside both subject silhouettes',
                      output=str(dest.relative_to(ROOT)))
        (folder / 'run.json').write_text(json.dumps(recipe, indent=2))
        STATE[direction] = {'output': str(dest.relative_to(ROOT)), 'frames': frames}; save()
        print('COMPOSITE', dest, flush=True)


if __name__ == '__main__': main()
