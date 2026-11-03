"""Exercise the layer/take UI and real canvas renderer; API requests use an isolated fixture."""
import base64
import copy
import json
import os
import subprocess
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT=Path('outputs/progress/scene-ui');OUT.mkdir(parents=True,exist_ok=True)
BASE=os.environ.get('TYPESET_UI_URL','http://127.0.0.1:5174')
PID='scenes-qa'
def img(color):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="{color}"/><circle cx="320" cy="180" r="70" fill="#eee"/></svg>'
    return 'data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()
def asset(id,color,layer=None):
    return dict(id=id,kind='image',path=img(color),name={'a':'Soft drift','b':'Blue turn','c':'Other layer','d':'New direction','ref':'Face reference'}.get(id,id),width=640,height=360,source=dict(kind='workflow',workflowId='wf',**(dict(layerId=layer) if layer else {})))
saved=dict(version=1,id=PID,name='Motion study · take comparison',width=640,height=360,fps=24,duration=5,media={},analysis={},shots=[],surfaces=[],grade=None,
    style=dict(fontFamily='Inter',fontWeight=700,fontSize=.1,fill='#ffffff',align='center'),look=dict(id='default'),
    words=[dict(id='caption',lineId='caption',text='fall',start=0,end=4,placement='overlay',preset='none',position=dict(x=.5,y=.8),autoPlace=False)],
    assets=[asset('a','#cc4455'),asset('b','#4466cc','star'),asset('c','#667766','sky'),asset('ref','#776655')],
    layers=[dict(id='star',name='Star motion',kind='media',assetId='a',start=0,**{'in':0},out=5,opacity=.9,transform=dict(x=.02,scale=1.1),keys=[dict(t=0,rotate=0),dict(t=3,rotate=3)]),
            dict(id='sky',name='Background texture',kind='media',assetId='c',start=0,**{'in':0},out=5,hidden=True)])
original_layer=copy.deepcopy(saved['layers'][0])
wf=dict(id='wf',name='Motion from reference',nodes=4,source='file',missing=[],output=dict(node='4',type='image'),candidates=dict(inputs=[],outputs=[]),
    inputs=dict(image=dict(node='1',field='image',role='media',kind='comfy_input_path',media='image',title='Identity'),
                prompt=dict(node='2',field='text',role='prompt',kind='string',title='Direction',default='Gentle movement'),
                seed=dict(node='3',field='seed',role='seed',kind='int',title='Sampler',default=12)))
jobs=[];runs=[];polls=0;errors=[]
checks=[]
def check(name,condition=True):
    assert condition,name
    checks.append(name)
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport=dict(width=1440,height=1000))
    page.on('pageerror',lambda e:errors.append(str(e)))
    def guard(route):
        global saved,polls
        req=route.request;path=req.url.split('/api/',1)[-1].split('?',1)[0]
        if path==f'projects/{PID}':
            if req.method=='PUT':saved=req.post_data_json
            route.fulfill(json=saved)
        elif path=='projects':route.fulfill(json=[saved])
        elif path=='health':route.fulfill(json=dict(comfyui=True,remote=None))
        elif path=='workflows':route.fulfill(json=[wf])
        elif path=='session':route.fulfill(json=dict(projectId=PID))
        elif path=='looks/saved':route.fulfill(json=[])
        elif path=='jobs':route.fulfill(json=jobs)
        elif path==f'projects/{PID}/workflows/wf/run':
            runs.append(req.post_data_json);jobs[:]=[dict(id='job-1',kind='workflow',status='running',projectId=PID,progress=.2,message='Generating takes')]
            route.fulfill(json=jobs[0])
        elif path=='jobs/job-1':
            polls+=1
            if polls>=3:
                a=asset('d','#9966cc',runs[-1].get('layerId'));a['source']['sceneId']=runs[-1].get('sceneId')
                jobs[0].update(status='done',progress=1,result=dict(assets=[a]))
                if not any(x['id']=='d' for x in saved['assets']):saved['assets'].append(a)
            route.fulfill(json=jobs[0])
        else:route.fulfill(status=404,json=dict(detail='Unavailable in isolated QA'))
    page.route('**/api/**',guard)
    def save():
        with page.expect_response(lambda r:r.request.method=='PUT' and f'projects/{PID}' in r.url):page.locator('.s-save').click()
        page.wait_for_timeout(50)
    def choose(name):page.get_by_role('button',name=f'Select scene {name}',exact=True).click()
    def take(name,n):return page.get_by_role('button',name=f'Preview {name} take {n}',exact=True)
    def undo():
        page.locator('.study-nav').first.click(position=dict(x=3,y=3));page.keyboard.press('Meta+z');page.wait_for_timeout(100)
    page.goto(f'{BASE}/#/studio?project={PID}')
    page.wait_for_selector('.scene-workspace');page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    panel=page.locator('.wf-panel')
    expect(page.get_by_role('button',name='Create',exact=True)).to_have_count(0)
    expect(page.get_by_role('button',name='Layers',exact=True)).to_have_count(0)
    choose('Star motion');expect(take('Star motion',2)).to_be_visible();check('Legacy clips become scenes with provenance takes')
    expect(page.locator('.ly-clip[data-layer-id="star"]')).to_have_class(__import__('re').compile('scene-linked'))
    panel.get_by_label('Direction',exact=True).fill('Wind and a head-only glance.')
    panel.get_by_label('Reference: Identity',exact=True).click();page.get_by_label('Search media',exact=True).fill('Face reference');page.get_by_role('button',name='Use Face reference',exact=True).click()
    panel.get_by_role('radio',name='2×',exact=True).click()
    choose('Background texture');expect(panel.get_by_label('Direction',exact=True)).to_have_value('Gentle movement')
    choose('Star motion');expect(panel.get_by_label('Direction',exact=True)).to_have_value('Wind and a head-only glance.');check('Scene recipes stay separate')
    take('Star motion',2).click();expect(page.get_by_role('region',name='Full take preview')).to_be_visible()
    expect(page.locator('.study-preview-box')).to_have_count(1);expect(page.locator('.scene-candidate-box')).to_be_visible()
    check('Full source preview marks the viewer and target clip')
    save();check('Source preview never enters saved timeline',saved['layers'][0]['assetId']=='a')
    take('Star motion',2).click();expect(page.get_by_role('region',name='Full take preview')).to_have_count(0)
    take('Star motion',2).click();choose('Star motion');expect(page.get_by_role('region',name='Full take preview')).to_have_count(0);check('Same take and scene both leave preview')
    take('Star motion',2).click();page.get_by_role('button',name='Preview take in edit',exact=True).click()
    page.wait_for_function("(()=>{const d=document.querySelector('#stage').getContext('2d').getImageData(100,100,1,1).data;return d[2]>d[0]*1.5})()")
    save();check('In-edit audition renders but is not saved',saved['layers'][0]['assetId']=='a')
    page.get_by_role('button',name='Replace selected clip',exact=True).click();save()
    check('Replace commits only source',saved['layers'][0]['assetId']=='b')
    for k in ['start','in','out','transform','opacity','keys']:check(f'Replace keeps {k}',saved['layers'][0][k]==original_layer[k])
    undo();save();check('Replace is undoable',saved['layers'][0]['assetId']=='a')
    take('Star motion',2).click();page.get_by_role('button',name='Add to timeline',exact=True).click();save()
    check('Add makes a clip in the same scene',len(saved['layers'])==3 and len(saved['board']['scenes'][0]['clips'])==2)
    take('Star motion',1).click();expect(page.get_by_role('region',name='Full take preview')).to_be_visible();check('Other takes still preview after adding')
    page.keyboard.press('Escape');choose('Star motion')
    # Select text from the real timeline: complete inspector, rendered preview, default cards.
    page.locator('.word-chip[data-word-id="caption"]').click()
    expect(page.get_by_role('textbox',name='Word text',exact=True)).to_be_visible()
    expect(page.get_by_alt_text('Selected text style preview')).to_be_visible();check('Timeline text opens full inspector and live style preview')
    page.get_by_role('button',name='Project default',exact=True).click();expect(page.locator('.s-right .looks-grid')).to_be_visible()
    expect(page.locator('.s-right .look-thumb img').first).to_be_visible(timeout=30000);check('Default styles use actual renderer thumbnails')
    # Fresh scene generation works without any clip. Switch scenes while job is running.
    page.get_by_role('button',name='New scene',exact=True).click();expect(page.get_by_label('Scene name',exact=True)).to_have_value('Scene 3')
    page.get_by_role('button',name='Add scene reference',exact=True).click();page.get_by_role('button',name='Attach Face reference',exact=True).click()
    expect(panel.locator('[data-reference-key="image"]')).to_have_attribute('data-reference-id','ref')
    panel.get_by_label('Direction',exact=True).fill('Silent scene, wind in hair.')
    panel.get_by_role('button',name='Generate take',exact=True).click()
    expect(panel.get_by_role('button',name=__import__('re').compile('Generating'))).to_be_visible()
    choose('Star motion');page.wait_for_timeout(3600)
    check('Run targets scene without a clip',not runs[-1].get('layerId') and bool(runs[-1].get('sceneId')))
    check('Run binds the explicit reference',runs[-1]['sources']['image']['assetId']=='ref')
    expect(take('Star motion',3)).to_have_count(0)
    choose('Scene 3');expect(take('Scene 3',1)).to_be_visible();check('Late result appears in its original scene')
    save();page.reload();page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    choose('Scene 3');expect(panel.get_by_label('Direction',exact=True)).to_have_value('Silent scene, wind in hair.');expect(take('Scene 3',1)).to_be_visible();check('Scene recipe and takes survive reload')
    # Infinite board: view gestures, body selection, rename, drag, deletion and undo.
    page.get_by_role('button',name='Board',exact=True).click();canvas=page.get_by_role('region',name='Scene board canvas')
    expect(canvas).to_be_visible();v=float(canvas.get_attribute('data-zoom'));canvas.hover();page.keyboard.down('Control');page.mouse.wheel(0,-90);page.keyboard.up('Control');page.wait_for_timeout(150)
    check('Board zoom works',float(canvas.get_attribute('data-zoom'))>v)
    page.get_by_role('button',name='Focus selected scene',exact=True).click()
    card=page.locator('.study-board-card.selected');card.locator('.scene-title').dblclick();name=card.locator('input');name.fill('Wind study');name.press('Enter');expect(page.get_by_label('Scene name',exact=True)).to_have_value('Wind study');check('Board and inspector share scene name')
    save();sid=page.locator('.study-board-card.selected').get_attribute('data-scene-id');oldxy=next((x['x'],x['y']) for x in saved['board']['scenes'] if x['id']==sid)
    box=card.bounding_box();page.mouse.move(box['x']+4,box['y']+8);page.mouse.down();page.mouse.move(box['x']+44,box['y']+48,steps=4);page.mouse.up();save()
    nowxy=next((x['x'],x['y']) for x in saved['board']['scenes'] if x['id']==sid);check('Dragging a board frame persists its position',nowxy!=oldxy)
    count=len(saved['layers']);assets=len(saved['assets']);canvas.focus();page.keyboard.press('Backspace');save()
    check('Delete removes grouping only',all(x['name']!='Wind study' for x in saved['board']['scenes']) and len(saved['layers'])==count and len(saved['assets'])==assets)
    canvas.focus();page.keyboard.press('Meta+z');save();check('Scene deletion is undoable',any(x['name']=='Wind study' for x in saved['board']['scenes']))
    page.screenshot(path=str(OUT/'isolated-board.png'))
    page.get_by_role('button',name='Scenes',exact=True).click();choose('Star motion');page.screenshot(path=str(OUT/'isolated-scenes.png'))
    # Real video sources remain independently previewable after placement.
    videos={}
    with tempfile.TemporaryDirectory() as tmp:
        for aid,color,duration in [('blue','#4466cc',4),('purple','#9966cc',3)]:
            target=Path(tmp)/f'{aid}.mp4'
            subprocess.run(['/opt/homebrew/bin/ffmpeg','-v','error','-y','-f','lavfi','-i',f'color=c={color}:s=160x96:r=24:d={duration}','-c:v','libx264','-pix_fmt','yuv420p',str(target)],check=True)
            videos[aid]=target.read_bytes();saved['assets'].append(dict(id=aid,kind='video',path=f'media/{aid}.mp4',name=f'{aid.title()} footage',duration=duration,width=160,height=96,fps=24,source=dict(kind='workflow',workflowId='wf',layerId='star')))
    page.route(f'**/files/projects/{PID}/media/*.mp4',lambda route:route.fulfill(body=videos[route.request.url.rsplit('/',1)[-1].split('.')[0]],content_type='video/mp4'))
    jobs.clear();page.reload();page.wait_for_selector('.stage-loading',state='hidden',timeout=60000);choose('Star motion')
    purple=page.locator('.study-take[title^="Purple footage"]');blue=page.locator('.study-take[title^="Blue footage"]')
    purple.click();page.get_by_role('button',name='Add to timeline',exact=True).click();save();accepted=copy.deepcopy(saved['layers'])
    for aid in ['blue','purple','blue']:
        page.locator(f'.study-take[title^="{aid.title()} footage"]').click();source=page.locator('.source-viewer video');expect(source).to_be_visible()
        page.wait_for_function("document.querySelector('.source-viewer video')?.readyState>=2")
        check(f'Full {aid} video source plays after adding',source.evaluate('(v)=>v.duration')==dict(blue=4,purple=3)[aid]);save();assert saved['layers']==accepted
    page.keyboard.press('Space');check('Space pauses source preview',source.evaluate('(v)=>v.paused'))
    blue.click();expect(page.locator('.source-viewer video')).to_have_count(0);blue.click();expect(page.locator('.source-viewer video')).to_be_visible();check('A used video can be previewed repeatedly')
    page.keyboard.press('Escape');page.get_by_role('button',name='Media',exact=True).click();expect(page.locator('#studio-left-panel').get_by_label('Footage grade',exact=True)).to_be_visible();check('Base-footage grading remains accessible')
    check('No browser exceptions',not errors)
    print(json.dumps(dict(checks=len(checks),passed=checks,errors=errors),indent=2));browser.close()
