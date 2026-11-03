"""Selection-driven generation QA; all fixture API calls are intercepted, never run on ComfyUI.

--live reads the Playboi project for visual review, with writes and jobs intercepted.
"""
import base64
import copy
import io
import json
import os
import re
import sys
import urllib.request
import wave
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('TYPESET_UI_URL', 'http://127.0.0.1:5174')
OUT = Path('outputs/progress/generation-context')
OUT.mkdir(parents=True, exist_ok=True)
checks = []
def check(name, condition=True):
    assert condition, name
    checks.append(name)

def image(aid, name, color='#6a7694'):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="{color}"/><circle cx="320" cy="180" r="80" fill="#ddd"/></svg>'
    return dict(id=aid, name=name, kind='image', width=640, height=360, path='data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode())

def workflow(wid, name):
    return dict(id=wid, name=name, nodes=12, source='file', missing=[], output=dict(node='4', type='video'), candidates=dict(inputs=[], outputs=[]),
        inputs=dict(image=dict(node='1',field='image',role='media',kind='comfy_input_path',media='image',title='Start frame (the person)'),
                    audio=dict(node='2',field='audio',role='media',kind='comfy_input_path',media='audio',title='Vocal (song window)'),
                    prompt=dict(node='3',field='text',role='prompt',kind='string',title='Direction',default='Gentle movement'),
                    seed=dict(node='4',field='seed',role='seed',kind='int',title='Sampler',default=12)))

def fixture():
    assets = [image('still-a', 'Red still', '#c64a50'), image('still-b', 'Blue still', '#506bc9'), image('loose', 'Loose pool still', '#26a694')]
    for key in ['a', 'b']:
        a = image(f'take-{key}', f'Take {key.upper()}', '#9958b3')
        a['source'] = dict(kind='workflow', workflowId='sing', sceneId='phrase', regeneration=dict(
            inputs=dict(prompt=f'Sing {key}',seed=509 if key=='a' else 510), sources=dict(image=f'still-{key}',audio='@prepared'),
            mediaFiles=dict(audio=dict(path=f'vocal-{key}.wav',name=f'Vocal {key.upper()}',duration=5)),
            postprocess=dict(timeScale=.8,trimStart=.25,fps=24,audio=f'song-{key}.wav')))
        assets.append(a)
    assets.extend(image(f'extra-{n}', f'Unrelated {n}') for n in range(80))
    scene = dict(id='phrase',name='Phrase',x=0,y=0,takes=['take-a','take-b','loose'],refs=['still-a','still-b'],clips=['clip'],
                 generation=dict(workflowId='sing',workflows=dict(sing=dict(inputs=dict(prompt='Scene prompt'),sources=dict(image='still-a',audio='@prepared'),mediaFiles=dict(audio=dict(path='scene.wav',name='Scene vocal',duration=5))))))
    return dict(version=1,id='generation-qa',name='Generation QA',width=640,height=360,fps=24,duration=5,media={},analysis={},shots=[],surfaces=[],grade=None,words=[],style=dict(fontFamily='Inter',fontWeight=700,fontSize=.1,fill='#ffffff',align='center'),look=dict(id='default'),assets=assets,
        layers=[dict(id='clip',kind='media',assetId='take-a',name='Phrase',start=0,**{'in':0},out=5,opacity=1)],board=dict(cards=[],scenes=[scene]))

live = '--live' in sys.argv
if live:
    pid = 'c82161a0-7774-4add-b974-bcc92461397a'
    saved = json.load(urllib.request.urlopen(f'http://127.0.0.1:8787/api/projects/{pid}'))
else:
    saved = fixture()
    pid = saved['id']
original = copy.deepcopy(saved)
runs, errors = [], []
audio = io.BytesIO()
with wave.open(audio, 'wb') as wav:
    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b'\0\0'*40000)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport=dict(width=1600, height=1000))
    page.on('pageerror', lambda e: errors.append(str(e)))
    def route_api(route):
        global saved
        req = route.request
        path = req.url.split('/api/', 1)[1].split('?', 1)[0]
        if path == f'projects/{pid}':
            if req.method == 'PUT' and not live:
                saved = req.post_data_json
            route.fulfill(json=saved)
        elif path == 'projects': route.fulfill(json=[saved])
        elif path == 'session': route.fulfill(json=dict(projectId=pid))
        elif path in ['jobs', 'looks/saved']: route.fulfill(json=[])
        elif live and req.method == 'GET': route.continue_()
        elif not live and path == 'health': route.fulfill(json=dict(comfyui=True, remote=None))
        elif not live and path == 'workflows': route.fulfill(json=[workflow('sing','Singing performance'),workflow('motion','Scene motion')])
        elif not live and path.endswith('/run'):
            runs.append(req.post_data_json)
            route.fulfill(json=dict(id='done',kind='workflow',status='done',projectId=pid,result=dict(assets=[])))
        else: route.fulfill(status=409, json=dict(detail='Blocked by isolated QA'))
    page.route('**/api/**', route_api)
    if not live:
        def route_audio(route):
            data=audio.getvalue();headers={'Accept-Ranges':'bytes'}
            match=re.match(r'bytes=(\d+)-(\d*)',route.request.headers.get('range',''))
            if match:
                start=int(match[1]);end=min(int(match[2]) if match[2] else len(data)-1,len(data)-1)
                headers['Content-Range']=f'bytes {start}-{end}/{len(data)}'
                route.fulfill(status=206,body=data[start:end+1],content_type='audio/wav',headers=headers)
            else: route.fulfill(body=data,content_type='audio/wav',headers=headers)
        page.route('**/files/projects/generation-qa/*.wav',route_audio)
    page.goto(f'{BASE}/#/studio?project={pid}')
    page.wait_for_selector('.s-save', timeout=60000)
    page.wait_for_selector('.stage-loading', state='hidden', timeout=60000)
    panel = page.locator('.wf-panel')
    def select(scene, n): page.get_by_role('button', name=f'Preview {scene} take {n}', exact=True).click()
    def reference(aid): expect(panel.locator('[data-reference-key="image"]')).to_have_attribute('data-reference-id', aid)
    def save():
        with page.expect_response(lambda r:r.request.method=='PUT' and f'projects/{pid}' in r.url): page.locator('.s-save').click()
    if live:
        page.get_by_role('button', name='Select scene Booth hook', exact=True).click()
        pool = next(a for a in saved['assets'] if a.get('name')=='Earlier · pool flash')
        page.locator('.study-take[title^="Earlier · pool flash"]').click()
        reference(pool['id'])
        check('Loose still selection actually supplies the displayed frame')
        page.screenshot(path=str(OUT/'live-pool.png'))
        page.get_by_role('button', name='Select scene Playboi · new positions & perspectives', exact=True).click()
        select('Playboi · new positions & perspectives', 1)
        reference('a_561901b65f')
        expect(panel.get_by_label('Workflow', exact=True)).to_contain_text('Singing performance')
        expect(panel.locator('[data-reference-key="audio"]')).to_have_attribute('data-reference-id','@prepared')
        page.wait_for_function("document.querySelector('.wf-audio-transport audio')?.readyState >= 1")
        check('Real take restores original workflow, still and loaded prepared vocal')
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT/'live-inspector.png'))
        panel.get_by_label('Reference: Start frame (the person)',exact=True).click()
        page.screenshot(path=str(OUT/'live-references.png'))
        check('References use a bounded visual picker', page.locator('dialog').bounding_box()['height'] < 950)
        page.keyboard.press('Escape')
        panel.get_by_label('Workflow',exact=True).click()
        check('Test fixture workflows no longer appear',page.get_by_role('button',name=re.compile('Use workflow SaveImage')).count()==0)
        page.screenshot(path=str(OUT/'live-workflows.png'))
    else:
        reference('still-a')
        select('Phrase',2);reference('still-b')
        expect(panel.get_by_label('Direction',exact=True)).to_have_value('Sing b')
        check('Clicking a take restores its own inputs without changing scene recipe')
        player=panel.locator('.wf-audio-transport audio')
        page.wait_for_function("document.querySelector('.wf-audio-transport audio')?.readyState >= 1")
        panel.get_by_role('button',name='Play Vocal B',exact=True).click()
        expect(panel.get_by_role('button',name='Pause Vocal B',exact=True)).to_be_visible()
        check('Compact vocal transport plays the actual prepared file',not player.evaluate('(a)=>a.paused'))
        panel.get_by_role('button',name='Pause Vocal B',exact=True).click()
        check('Compact vocal transport pauses',player.evaluate('(a)=>a.paused'))
        scrubber=panel.get_by_label('Seek Vocal B',exact=True)
        scrubber.focus();scrubber.press('Home');scrubber.press('ArrowRight')
        page.wait_for_function("document.querySelector('.wf-audio-transport audio').currentTime > 0")
        check('Vocal scrubber seeks the prepared audio',abs(player.evaluate('(a)=>a.currentTime')-float(scrubber.input_value()))<.001 and float(scrubber.input_value())>0)
        panel.get_by_label('Direction',exact=True).fill('Turn gently')
        select('Phrase',1);reference('still-a');expect(panel.get_by_label('Direction',exact=True)).to_have_value('Sing a')
        select('Phrase',2);expect(panel.get_by_label('Direction',exact=True)).to_have_value('Turn gently')
        check('Edits stay with their take when switching')
        check('Inspector has no long native asset or workflow dropdowns',panel.locator('select').count()==0)
        expect(panel.get_by_label('Seed: Sampler',exact=True)).not_to_be_visible()
        check('Advanced settings are collapsed by default')
        select('Phrase',3);reference('loose')
        panel.get_by_label('Reference: Vocal (song window)',exact=True).click()
        page.get_by_role('dialog').get_by_role('button',name=re.compile('Scene vocal')).click()
        reference('loose')
        check('Changing vocal on a loose still keeps the selected image')
        panel.get_by_label('Direction',exact=True).fill('Pool singing')
        reference('loose');save();select('Phrase',1);select('Phrase',3);reference('loose')
        check('Loose still overrides stale scene image and keeps that binding after editing')
        panel.get_by_role('button',name='Generate take',exact=True).click()
        page.wait_for_timeout(100)
        check('Generation sends the selected loose frame',runs[-1]['sources']['image']['assetId']=='loose')
        check('Loose still keeps scene vocal',runs[-1]['sources']['audio']['path']=='scene.wav')
        select('Phrase',2)
        panel.get_by_label('Reference: Start frame (the person)',exact=True).click()
        dialog = page.get_by_role('dialog')
        dialog.get_by_role('button',name='Close picker',exact=True).focus();page.keyboard.press('Shift+Tab')
        check('Picker traps keyboard focus',dialog.evaluate('(d)=>d.contains(document.activeElement)'))
        check('Picker starts with this shot, not all project media',dialog.locator('.generation-media-grid>button').count()<10)
        dialog.get_by_role('button',name='All media · 85',exact=True).click()
        check('Large library stays in a bounded scroll area',dialog.bounding_box()['height']<=720 and dialog.locator('.generation-picker-scroll').evaluate('(e)=>e.scrollHeight>e.clientHeight'))
        dialog.get_by_label('Search media',exact=True).fill('Unrelated 73')
        expect(dialog.locator('.generation-media-grid>button')).to_have_count(1)
        dialog.get_by_role('button',name='Use Unrelated 73',exact=True).click();reference('extra-73')
        check('Search finds and assigns a reference without an ocean of options')
        panel.get_by_label('Reference: Start frame (the person)',exact=True).click()
        page.get_by_label('Search media',exact=True).fill('Red')
        page.keyboard.press('Escape');reference('extra-73')
        check('Escape dismisses the picker without changing references')
        target = panel.locator('[data-reference-key="image"]')
        data = page.evaluate_handle("()=>{const d=new DataTransfer();d.setData('application/x-typeset-asset','still-b');return d}")
        target.dispatch_event('drop',dict(dataTransfer=data));reference('still-b')
        check('A frame can be dropped directly on a reference tile')
        panel.get_by_label('Workflow',exact=True).click()
        page.get_by_label('Search workflows',exact=True).fill('motion')
        page.get_by_role('button',name='Use workflow Scene motion',exact=True).click()
        expect(panel.get_by_label('Workflow',exact=True)).to_contain_text('Scene motion')
        reference('still-b')
        panel.get_by_label('Workflow',exact=True).click()
        page.get_by_role('button',name='Use workflow Singing performance',exact=True).click()
        expect(panel.get_by_label('Direction',exact=True)).to_have_value('Turn gently')
        check('Workflow switching preserves the edited recipe')
        panel.get_by_label('Generation settings',exact=True).click()
        expect(panel.get_by_label('Seed: Sampler',exact=True)).to_have_value('510')
        panel.get_by_label('Generation settings',exact=True).click()
        panel.get_by_role('button',name='Generate take',exact=True).click()
        page.wait_for_timeout(100)
        check('Generation restores exact prepared vocal and output timing',runs[-1]['sources']['audio']==dict(path='vocal-b.wav',start=0,end=5) and runs[-1]['postprocess']['trimStart']==.25)
        check('Generation uses edited prompt and original seed',runs[-1]['inputs']['prompt']=='Turn gently' and runs[-1]['inputs']['seed']==510)
        save();check('Preview and reference edits leave timeline intact',saved['layers']==original['layers'])
        check('Selection edits never overwrite original asset provenance',saved['assets']==original['assets'])
        page.reload();page.wait_for_selector('.s-save');select('Phrase',2);reference('still-b')
        expect(panel.get_by_label('Direction',exact=True)).to_have_value('Turn gently')
        check('Per-take edits survive reload')
        page.get_by_role('button',name='Board',exact=True).click()
        page.get_by_role('button',name='Fullscreen board',exact=True).click()
        select('Phrase',3)
        page.get_by_role('button',name='Exit fullscreen board',exact=True).click();reference('loose')
        expect(panel.get_by_label('Direction',exact=True)).to_have_value('Pool singing')
        check('A take selected on the fullscreen board supplies generation context')
        page.screenshot(path=str(OUT/'fixture.png'))
    check('No browser exceptions',not errors)
    print(json.dumps(dict(checks=len(checks),passed=checks,errors=errors),indent=2))
    browser.close()
