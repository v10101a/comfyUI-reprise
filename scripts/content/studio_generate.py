"""Submit a real Studio Create action from a saved, reproducible direction.

Only the selected clip's generation draft is changed; the browser uses the normal
Create button. The request, job and screenshot are saved beside the song review.
"""
import argparse
import copy
import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect


def open_generation(page, cfg, project):
    if cfg.get('scene'):
        scene = next(s for s in project['board']['scenes'] if s['id'] == cfg['scene'])
        page.get_by_role('button', name='Scenes', exact=True).first.click()
        page.get_by_role('button', name='Select scene '+scene['name'], exact=True).click()
        page.locator('.scene-inspector-tabs').get_by_role('button', name='Generate', exact=True).click()
    else:
        page.get_by_role('button', name='Create', exact=True).click()
        page.locator('.wf-panel').get_by_label('Reference clip').select_option(cfg['layer'])
    return page.locator('.wf-panel')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config', type=Path)
    ap.add_argument('--collect', action='store_true')
    ap.add_argument('--preview', action='store_true')
    ap.add_argument('--wait', action='store_true', help='Wait for existing Studio workflow jobs in this project before submitting')
    ap.add_argument('--prepare-motion', action='store_true', help='Prepare matching motion history and its exact last frame for a singing follow-up')
    args = ap.parse_args()
    cfg = json.loads(args.config.read_text())
    out = args.config.parent
    api = httpx.Client(base_url='http://127.0.0.1:8787', timeout=90)
    pid, lid, wid = cfg['project'], cfg['layer'], cfg['workflow']
    if (args.preview or args.collect or args.prepare_motion) and not (out / (cfg['name'] + '.submitted.json')).exists():
        print(json.dumps({'name':cfg['name'],'status':'not submitted yet'})); return
    if args.prepare_motion:
        submitted=json.loads((out/(cfg['name']+'.submitted.json')).read_text())
        job=api.get('/api/jobs/'+submitted['job']['id']).json()
        if job['status']!='done': print(json.dumps({'status':job['status']})); return
        follow=cfg['motionFollowup']; asset=job['result']['assets'][0]
        root=Path('data/projects')/pid
        work=out.parents[1]/'motion/fresh'/cfg['name']; work.mkdir(parents=True,exist_ok=True)
        n=follow['frames']
        motion=work/'history.mp4'; frame=work/'last_frame.png'
        subprocess.run(['ffmpeg','-v','error','-y','-ss','0.75','-i',str(root/asset['path']),
                        '-vf','setpts=PTS/0.8,fps=16,scale=1152:656','-frames:v',str(n),'-an',
                        '-c:v','libx264','-crf','16',str(motion)],check=True)
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(motion),'-vf',f'select=eq(n\\,{n-1})',
                        '-frames:v','1',str(frame)],check=True)
        ids_path=work/'assets.json'
        ids=json.loads(ids_path.read_text()) if ids_path.exists() else {}
        for key,file,mime in [('motion',motion,'video/mp4'),('image',frame,'image/png')]:
            if key not in ids:
                with file.open('rb') as fh:
                    r=api.post(f'/api/projects/{pid}/assets',files={'file':(file.name,fh,mime)},
                               data={'addLayer':'false','name':cfg['title']+' · '+key+' reference'})
                r.raise_for_status(); ids[key]=r.json()['id']; ids_path.write_text(json.dumps(ids,indent=2))
        p=api.get(f'/api/projects/{pid}').json()
        original=next(l for l in p['layers'] if l['id']==lid)['generation']['workflows']['ed3fbc575706']
        draft=copy.deepcopy(original)
        draft['sources'].update(ids)
        draft['inputs'].update(motion_frames=n,seed=101+follow['index']*12,
            prompt="Continue the same real moving-escalator scene and camera travel shown in the supplied motion reference. The exact same person sings the supplied vocal quietly and naturally, with small relaxed lip movements and an easy jaw, calm tired eyes, no acting or toothy expression. They ride along with a slight natural sway and a small glance ahead; their short hair and coat collar stir gently. The station, railings and lights travel smoothly past in a physically continuous perspective. Keep the station geometry stable and the motion steady. Same face, silver septum and lip rings, silver-blue short hair with dark underneath, black leather coat and flat chest. Real grainy film, natural skin, coherent unbroken shot.")
        result=dict(name=follow['name'],title=follow['title'],project=pid,layer=lid,workflow='3e6e616563a1',draft=draft,
                    boardGroup=cfg['boardGroup'],boardIndex=follow['index'],
                    conditioning={'sourceAsset':asset['id'],'sourceStart':.75,'historyFrames':n,'referenceIsLastHistoryFrame':True})
        target=out/(follow['name']+'.json'); target.write_text(json.dumps(result,indent=2))
        print(json.dumps({'config':str(target),'references':ids,'frames':n})); return
    if args.preview:
        submitted = json.loads((out / (cfg['name'] + '.submitted.json')).read_text())
        job = api.get('/api/jobs/' + submitted['job']['id']).json()
        assert job['status'] == 'done', job['status']
        aid = job['result']['assets'][0]['id']
        current = api.get(f'/api/projects/{pid}').json()
        a = next(a for a in current['assets'] if a['id'] == aid)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width':1600,'height':1100})
            page.goto(f'http://127.0.0.1:5174/#/studio?project={pid}')
            page.wait_for_selector('.stage-loading', state='hidden', timeout=60000)
            panel = open_generation(page, cfg, current)
            if cfg.get('scene'):
                button = page.get_by_title(a['name']+' · Drag to timeline', exact=True).or_(
                    page.get_by_title(a['name']+' · Used on timeline · Drag to timeline', exact=True)).first
            else:
                button = panel.get_by_role('option',name='Preview '+a['name'],exact=True)
                if button.count() == 0: panel.get_by_role('button',name='Show all',exact=False).click()
            button.click()
            viewer = page.get_by_role('region',name='Full take preview')
            if a['kind'] == 'video':
                page.wait_for_function('document.querySelector(".source-viewer video")?.readyState >= 2')
                video = viewer.locator('video')
                video.evaluate('(v)=>{v.pause(); v.currentTime=Math.min(1.5,v.duration/2)}')
                page.wait_for_timeout(400)
                info = video.evaluate('(v)=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,source:v.currentSrc})')
                assert abs(info['duration']-a['duration']) < .05, info
            else:
                expect(viewer.locator('img')).to_be_visible(); info = {'image':True}
            page.screenshot(path=str(out / (cfg['name'] + '.preview.png')))
            browser.close()
        print(json.dumps({'asset':aid,'preview':info})); return
    if args.collect:
        submitted = json.loads((out / (cfg['name'] + '.submitted.json')).read_text())
        r = api.get('/api/jobs/' + submitted['job']['id']); r.raise_for_status(); job = r.json()
        (out / (cfg['name'] + '.job.json')).write_text(json.dumps(job, indent=2))
        if job['status'] != 'done':
            print(json.dumps({k: job.get(k) for k in ('id', 'status', 'message')})); return
        asset = job['result']['assets'][0]
        root = Path('data/projects') / pid
        category = 'clips' if cfg.get('category') == 'scene' else 'singing'
        dest = out.parents[1] / (category if asset['kind'] == 'video' else 'lookbook_v4/dramatic') / cfg['name']
        dest.mkdir(parents=True, exist_ok=True)
        extension = ('.mp4' if cfg.get('category') == 'scene' else '_mux.mp4') if asset['kind'] == 'video' else '.png'
        media = dest / (cfg['name'] + extension)
        shutil.copy2(root / asset['path'], media)
        (dest / 'studio_job.json').write_text(json.dumps(job, indent=2))
        (dest / 'studio_recipe.json').write_text(json.dumps(submitted, indent=2))
        if asset['kind'] == 'video':
            sample_rate = min(2, 8 / max(float(asset.get('duration') or 4), .1))
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(media), '-vf',
                f'fps={sample_rate:.6f},scale=480:-1,tile=4x2', '-frames:v', '1', str(dest / 'strip.jpg')], check=True)
        if cfg.get('title'):
            for attempt in range(5):
                current = api.get(f'/api/projects/{pid}').json()
                updated = copy.deepcopy(current)
                a = next(a for a in updated['assets'] if a['id'] == asset['id'])
                a['name'] = cfg['title']
                a.setdefault('source', {}).update(importedFrom=str(media), regeneration=cfg['draft'])
                if cfg.get('parentAsset'): a['source']['parentAssetId'] = cfg['parentAsset']
                if cfg.get('phrase'): a['source']['phrase'] = cfg['phrase']
                if cfg.get('reviewNote'): a['source']['reviewNote'] = cfg['reviewNote']
                if cfg.get('scene'):
                    assert a['source'].get('sceneId') == cfg['scene'], 'Generation lost its scene provenance'
                    scene = next(s for s in updated['board']['scenes'] if s['id'] == cfg['scene'])
                    scene['takes'] = list(dict.fromkeys([*scene.get('takes', []), a['id']]))
                if cfg.get('boardGroup'):
                    cards = updated.setdefault('board', {}).setdefault('cards', [])
                    gid = cfg['boardGroup']['id']
                    group = next((c for c in cards if c['id'] == gid), None)
                    if group is None:
                        y = max((c.get('y',0)+c.get('h',0) for c in cards), default=0)+60
                        group = dict(id=gid, kind='group', title=cfg['boardGroup']['title'], x=0,y=y,w=1550,h=390,role='motion')
                        cards.append(group)
                    group['title'] = cfg['boardGroup']['title']
                    cid = 'card-'+cfg['name']
                    index = cfg.get('boardIndex',0)
                    card = dict(id=cid,kind='asset',title=cfg['title'],assetId=a['id'],layerId=lid,
                                x=24+(index%3)*490,y=group['y']+70+(index//3)*310,w=466,h=275,
                                role='reference' if a['kind']=='image' else 'motion')
                    old = next((c for c in cards if c['id']==cid),None)
                    if old is None: cards.append(card)
                    else:
                        old['title']=card['title']
                        if not any(l['id'] == old.get('layerId') for l in updated['layers']):
                            old['layerId'] = lid
                        if cfg.get('relocateBoardCard'):
                            old.update(card)
                    group['h'] = max(group['h'], 80+((index//3)+1)*310)
                if api.get(f'/api/projects/{pid}').json() != current: continue
                r = api.put(f'/api/projects/{pid}',json=updated); r.raise_for_status()
                saved = r.json()
                assert all(saved.get(k)==current.get(k) for k in ('layers','media','words'))
                break
            else: raise RuntimeError('Concurrent edits prevented naming the collected take')
        print(json.dumps({'status': job['status'], 'asset': asset['id'], 'file': str(media), 'duration': asset.get('duration')}))
        return
    if args.wait:
        deadline = time.monotonic()+7200
        announced = False
        while time.monotonic() < deadline:
            jobs = api.get('/api/jobs',params={'projectId':pid}).json()
            active = [j for j in jobs if j['kind']=='workflow' and j['status'] in ('queued','running')]
            if not active: break
            if not announced:
                print(json.dumps({'waitingFor':[j['id'] for j in active],'next':cfg['name']}),flush=True); announced=True
            time.sleep(3)
        else: raise TimeoutError('Existing Studio jobs did not finish')
    r = api.get(f'/api/projects/{pid}'); r.raise_for_status(); p = r.json()
    before = copy.deepcopy(p)
    target = (next(s for s in p['board']['scenes'] if s['id'] == cfg['scene']) if cfg.get('scene')
              else next(l for l in p['layers'] if l['id'] == lid))
    draft = copy.deepcopy(cfg['draft'])
    for item in draft.get('mediaFiles', {}).values():
        if 'duration' not in item:
            raw = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=nw=1:nk=1', str(Path('data/projects') / pid / item['path'])])
            item['duration'] = float(raw)
    cfg['draft'] = draft
    args.config.write_text(json.dumps(cfg, indent=2))
    gen = target.setdefault('generation', {})
    gen.setdefault('workflows', {})[wid] = draft
    gen['workflowId'] = wid
    # Never write an old project over a concurrent edit.
    fresh = api.get(f'/api/projects/{pid}').json()
    assert fresh == before, 'Project changed during preparation; rerun with fresh state'
    (out / (cfg['name'] + '.before.json')).write_text(json.dumps(before, indent=2))
    r = api.put(f'/api/projects/{pid}', json=p); r.raise_for_status()
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1600, 'height': 1100})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(f'http://127.0.0.1:5174/#/studio?project={pid}')
        page.wait_for_selector('.stage-loading', state='hidden', timeout=60000)
        panel = open_generation(page, cfg, p)
        expect(panel.get_by_label('Workflow', exact=True)).to_have_value(wid)
        # Fill through the actual form, including direction and seed.
        meta = api.get(f'/api/workflows/{wid}').json()
        for key in ('prompt', 'seed'):
            if key in draft['inputs']:
                spec = meta['inputs'][key]
                label = ('Seed: ' if key == 'seed' else '') + spec['title']
                panel.get_by_role('textbox' if key == 'prompt' else 'spinbutton', name=label, exact=True).fill(str(draft['inputs'][key]))
        run = panel.get_by_role('button', name='Generate take', exact=True)
        expect(run).to_be_enabled(timeout=30000)
        page.screenshot(path=str(out / (cfg['name'] + '.create.png')))
        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith(f'/workflows/{wid}/run'), timeout=60000) as started:
            run.click()
        response = started.value
        assert response.ok, response.text()
        job = response.json()
        submitted = response.request.post_data_json
        assert submitted['sources']['audio']['path'] == draft['mediaFiles']['audio']['path'] if 'audio' in draft.get('mediaFiles', {}) else True
        if cfg.get('scene'): assert submitted['sceneId'] == cfg['scene']
        else: assert submitted['layerId'] == lid
        (out / (cfg['name'] + '.submitted.json')).write_text(json.dumps({'config': cfg, 'request': submitted, 'job': job, 'browserErrors': errors}, indent=2))
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out / (cfg['name'] + '.running.png')))
        browser.close()
    print(json.dumps({'name': cfg['name'], 'job': job['id'], 'status': job['status'], 'browserErrors': errors}), flush=True)


if __name__ == '__main__':
    main()
