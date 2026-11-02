"""Exercise the layer/take UI and real canvas renderer; API requests use an isolated fixture."""
import base64
import copy
import json
import os
import subprocess
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT=Path('outputs/progress/takes');OUT.mkdir(parents=True,exist_ok=True)
BASE=os.environ.get('TYPESET_UI_URL','http://127.0.0.1:5174')
PID='takes-qa'
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
        elif path=='jobs':route.fulfill(json=jobs)
        elif path==f'projects/{PID}/workflows/wf/run':
            body=req.post_data_json;runs.append(body)
            jobs[:]=[dict(id='job-1',kind='workflow',status='running',projectId=PID,progress=.2,message='Generating takes')]
            route.fulfill(json=jobs[0])
        elif path=='jobs/job-1':
            polls+=1
            if polls>=3:
                a=asset('d','#9966cc',runs[-1].get('layerId'));jobs[0].update(status='done',progress=1,result=dict(assets=[a]))
                if not any(x['id']=='d' for x in saved['assets']):saved['assets'].append(a)
            route.fulfill(json=jobs[0])
        else:route.fulfill(status=404,json=dict(detail='Unavailable in isolated QA'))
    page.route('**/api/**',guard)
    page.goto(f'{BASE}/#/studio?project={PID}')
    page.wait_for_selector('.stage-wrap');page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    panel=page.locator('.wf-panel');layer_select=panel.get_by_label('Reference clip')
    layer_select.select_option('star')
    # All generated footage is visible by default; filtering is only for recipe-focused comparison.
    expect(panel.get_by_role('option',name='Preview Other layer',exact=True)).to_be_visible()
    panel.get_by_role('radio',name='This clip',exact=True).click()
    expect(panel.get_by_role('option',name='Preview Soft drift',exact=True)).to_be_visible()
    expect(panel.get_by_role('option',name='Preview Other layer',exact=True)).to_have_count(0)
    panel.get_by_label('Direction',exact=True).fill('Head stays forward, glance to the side. Wind in hair.')
    panel.get_by_label('Reference: Identity',exact=True).select_option('ref')
    panel.get_by_role('radio',name='2×',exact=True).click()
    layer_select.select_option('sky')
    expect(panel.get_by_label('Direction',exact=True)).to_have_value('Gentle movement')
    panel.get_by_label('Direction',exact=True).fill('Clouds drift slowly.')
    layer_select.select_option('star')
    expect(panel.get_by_label('Direction',exact=True)).to_have_value('Head stays forward, glance to the side. Wind in hair.')
    expect(panel.get_by_label('Reference: Identity',exact=True)).to_have_value('ref')
    pixel="Array.from(document.querySelector('#stage').getContext('2d').getImageData(100,100,1,1).data)"
    page.wait_for_function('''()=>{const c=document.querySelector('#stage'),d=c.getContext('2d').getImageData(100,100,1,1).data;return d[0]>d[2]*1.5}''')
    before=page.evaluate(pixel)
    panel.get_by_role('option',name='Preview Blue turn',exact=True).click()
    expect(page.get_by_role('region',name='Full take preview')).to_be_visible()
    expect(page.locator('.source-viewer img')).to_have_attribute('src',saved['assets'][1]['path'])
    panel.get_by_role('button',name='Candidate',exact=True).click()
    expect(page.get_by_text('Candidate preview',exact=True)).to_be_visible()
    expect(panel.get_by_role('option',name='Preview Blue turn',exact=True)).to_have_attribute('aria-selected','true')
    page.wait_for_function('''()=>{const d=document.querySelector('#stage').getContext('2d').getImageData(100,100,1,1).data;return d[2]>d[0]*1.5}''')
    candidate=page.evaluate(pixel)
    page.screenshot(path=str(OUT/'candidate.png'))
    with page.expect_response(lambda r:r.request.method=='PUT' and f'projects/{PID}' in r.url):page.locator('.s-save').click()
    assert saved['layers'][0]['assetId']=='a','Preview leaked into save'
    panel.get_by_role('button',name='Current',exact=True).click()
    page.wait_for_function('''()=>{const d=document.querySelector('#stage').getContext('2d').getImageData(100,100,1,1).data;return d[0]>d[2]*1.5}''')
    panel.get_by_role('button',name='Candidate',exact=True).click()
    panel.get_by_role('button',name='Replace selected clip',exact=True).click()
    with page.expect_response(lambda r:r.request.method=='PUT' and f'projects/{PID}' in r.url):page.locator('.s-save').click()
    committed=copy.deepcopy(saved['layers'][0]);assert committed['assetId']=='b'
    for k in ['start','in','out','transform','opacity','keys']:assert committed[k]==original_layer[k],k
    assert committed['takes']==['a','b']
    page.keyboard.press('Meta+z')
    with page.expect_response(lambda r:r.request.method=='PUT' and f'projects/{PID}' in r.url):page.locator('.s-save').click()
    assert saved['layers'][0]['assetId']=='a','Replace selected clip was not undoable'
    page.reload();page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    layer_select=page.locator('.wf-panel').get_by_label('Reference clip');layer_select.select_option('star')
    panel.get_by_role('radio',name='This clip',exact=True).click()
    expect(panel.get_by_label('Direction',exact=True)).to_have_value('Head stays forward, glance to the side. Wind in hair.')
    expect(panel.get_by_label('Reference: Identity',exact=True)).to_have_value('ref')
    panel.get_by_role('button',name='Generate 2 takes',exact=True).click()
    page.wait_for_function("document.querySelector('.wf-panel').textContent.includes('Generating')")
    layer_select.select_option('sky')
    # A late result is attached to the layer captured when Generate was clicked.
    page.wait_for_timeout(3600)
    expect(panel.get_by_role('option',name='Preview New direction',exact=True)).to_have_count(0)
    layer_select.select_option('star')
    expect(panel.get_by_role('option',name='Preview New direction',exact=True)).to_be_visible(timeout=10000)
    assert runs[0]['layerId']=='star' and runs[0]['variants']==2 and runs[0]['sources']['image']['assetId']=='ref'
    assert 'takeOf' not in runs[0] and not runs[0].get('remote')
    assert saved['layers'][0]['assetId']=='a','Generation applied a take without asking'
    page.screenshot(path=str(OUT/'workspace.png'))
    page.locator('.word-chip[data-word-id="caption"]').click()
    expect(page.locator('.ly-insp')).to_have_count(0)
    expect(page.get_by_role('textbox',name='Word text',exact=True)).to_be_visible()
    expect(layer_select).to_have_value('')
    layer_select.select_option('star')
    panel.get_by_role('option',name='Preview Blue turn',exact=True).click()
    page.keyboard.press('Escape')
    expect(page.get_by_text('Candidate preview',exact=True)).to_have_count(0)
    # Readiness belongs to the chosen host, and every blocked button explains why.
    wf.update(target='remote',missingModels=['video.safetensors'])
    page.reload();layer_select.select_option('star')
    generate=panel.get_by_role('button',name='Generate 2 takes',exact=True)
    expect(generate).to_be_disabled()
    expect(panel.locator('#wf-run-status')).to_contain_text('needs models')
    wf['missingModels']=[]
    panel.locator('#wf-run-status').get_by_role('button',name='Check again').click()
    expect(generate).to_be_enabled()
    expect(panel.locator('#wf-run-status')).to_have_text('Runs on remote GPU.')
    polls=0
    generate.click()
    page.wait_for_function("document.querySelector('.wf-panel').textContent.includes('Generating')")
    assert runs[-1]['remote'] is True,'Generate must submit to the host whose readiness was checked'
    page.wait_for_timeout(3600)
    wf['readinessError']='Cannot reach ComfyUI. Check the connection and try again.'
    page.reload();layer_select.select_option('star')
    expect(generate).to_be_disabled()
    expect(panel.locator('#wf-run-status')).to_contain_text('Cannot reach ComfyUI')

    # Use two actual video takes as independent footage, then cut pieces from both.
    videos={}
    with tempfile.TemporaryDirectory() as tmp:
        for aid,color,duration in [('blue','#4466cc',4),('purple','#9966cc',3)]:
            target=Path(tmp)/f'{aid}.mp4'
            subprocess.run(['/opt/homebrew/bin/ffmpeg','-v','error','-y','-f','lavfi','-i',
                            f'color=c={color}:s=160x96:r=24:d={duration}','-c:v','libx264','-pix_fmt','yuv420p',str(target)],check=True)
            videos[aid]=target.read_bytes()
            saved['assets'].append(dict(id=aid,kind='video',path=f'media/{aid}.mp4',name=f'{aid.title()} footage',duration=duration,width=160,height=96,fps=24,
                                        source=dict(kind='workflow',workflowId='wf',layerId='star')))
    page.route(f'**/files/projects/{PID}/media/*.mp4',lambda route:route.fulfill(
        body=videos[route.request.url.rsplit('/',1)[-1].split('.')[0]],content_type='video/mp4'))
    wf.pop('readinessError');jobs.clear();page.reload()
    page.wait_for_selector('.ly-clip')
    def save():
        with page.expect_response(lambda r:r.request.method=='PUT' and f'projects/{PID}' in r.url):page.locator('.s-save').click()
    save();original=copy.deepcopy(saved['layers'])
    # Add at the playhead is also available while an existing clip is selected.
    panel.get_by_role('option',name='Preview Purple footage',exact=True).click()
    panel.get_by_role('button',name='Add to timeline',exact=True).click()
    expect(page.locator('.ly-clip')).to_have_count(3);save()
    added=next(l for l in saved['layers'] if l['id'] not in [x['id'] for x in original])
    assert added['assetId']=='purple' and added['out']==3
    assert saved['layers'][:2]==original
    # Adding footage selects a new clip. Every source must still preview in full, including
    # the already-used take, without the new clip's trim/position/stack obscuring the source.
    accepted=copy.deepcopy(saved['layers']);added_id=added['id']
    for aid in ('blue','purple','blue'):
        panel.get_by_role('option',name=f'Preview {aid.title()} footage',exact=True).click()
        source=page.locator('.source-viewer video');expect(source).to_be_visible()
        expect(source).to_have_attribute('src',f'/files/projects/{PID}/media/{aid}.mp4')
        page.wait_for_function("document.querySelector('.source-viewer video')?.readyState>=2")
        assert source.evaluate('(v)=>v.duration')==({'blue':4,'purple':3}[aid])
        expect(layer_select).to_have_value(added_id)
        save();assert saved['layers']==accepted,'Source preview changed the timeline'
    # A finished source can be clicked again to replay; Space controls this video, not the edit.
    source.evaluate('''async v=>{v.currentTime=v.duration-.05;await v.play();}''')
    page.wait_for_function("document.querySelector('.source-viewer video').ended")
    panel.get_by_role('option',name='Preview Blue footage',exact=True).click()
    page.wait_for_function("!document.querySelector('.source-viewer video').paused && document.querySelector('.source-viewer video').currentTime<1")
    timecode=page.locator('.source-transport').text_content()
    page.keyboard.press('Space');assert source.evaluate('(v)=>v.paused')
    page.keyboard.press('ArrowRight');assert page.locator('.source-transport').text_content()==timecode
    page.screenshot(path=str(OUT/'repeated-source-preview.png'))
    page.keyboard.press('Escape');expect(page.get_by_role('region',name='Full take preview')).to_have_count(0)
    expect(layer_select).to_have_value(added_id)
    # The full viewer also works without a reference clip selected.
    layer_select.select_option('');panel.get_by_role('option',name='Preview Purple footage',exact=True).click()
    expect(page.locator('.source-viewer video')).to_be_visible()
    page.locator(f'.ly-clip[data-layer-id="{added_id}"]').click()
    expect(page.get_by_role('region',name='Full take preview')).to_have_count(0)
    panel.get_by_role('option',name='Preview Purple footage',exact=True).click()
    page.locator('.source-preview-status').get_by_role('button',name='Return to edit',exact=True).click()
    layer_select.select_option(added_id)
    page.keyboard.press('Meta+z');expect(page.locator('.ly-clip')).to_have_count(2)
    # Dragging a take after the edit appends its full source, preserving the original cut.
    drop=page.locator('.tl-add-media .tl-body');box=drop.bounding_box()
    panel.get_by_role('option',name='Preview Blue footage',exact=True).drag_to(drop,target_position=dict(x=box['width']-2,y=14))
    expect(page.get_by_label('Timeline length in seconds')).to_have_value('9.00');save()
    assert saved['layers'][:2]==original
    blue=next(l for l in saved['layers'] if l['assetId']=='blue')
    assert [blue['start'],blue['in'],blue['out']]==[5,0,4]
    assert blue['generation']==original[0]['generation']
    def seek(t):
        ruler=page.locator('.tl-ruler');box=ruler.bounding_box()
        page.mouse.click(box['x']+box['width']*t/float(page.get_by_label('Timeline length in seconds').input_value()),box['y']+27)
    seek(7)
    page.get_by_role('button',name='Split selected clip',exact=True).click()
    expect(page.locator('.ly-clip')).to_have_count(4);save()
    assert [[l['start'],l['in'],l['out']] for l in saved['layers'] if l['assetId']=='blue']==[[5,0,2],[7,2,4]]
    page.keyboard.press('Meta+z');expect(page.locator('.ly-clip')).to_have_count(3)
    page.keyboard.press('Meta+Shift+z');expect(page.locator('.ly-clip')).to_have_count(4)
    page.keyboard.press('Backspace');expect(page.locator('.ly-clip')).to_have_count(3)
    box=drop.bounding_box()
    panel.get_by_role('option',name='Preview Purple footage',exact=True).drag_to(drop,target_position=dict(x=box['width']*7/9,y=14))
    expect(page.get_by_label('Timeline length in seconds')).to_have_value('10.00')
    seek(8);page.keyboard.press('Meta+b');expect(page.locator('.ly-clip')).to_have_count(5)
    page.keyboard.press('Backspace');expect(page.locator('.ly-clip')).to_have_count(4);save()
    assert saved['layers'][:2]==original
    edited=[l for l in saved['layers'] if l['assetId'] in ['blue','purple']]
    assert [[l['assetId'],l['start'],l['in'],l['out']] for l in edited]==[['blue',5,0,2],['purple',7,0,1]]
    assert len([a for a in saved['assets'] if a['id'] in ['blue','purple']])==2
    page.reload();expect(page.locator('.ly-clip')).to_have_count(4)
    seek(7.5)
    page.wait_for_function('''()=>{const d=document.querySelector('#stage').getContext('2d').getImageData(100,100,1,1).data;return d[0]>140&&d[0]<165&&d[2]>190}''')
    page.screenshot(path=str(OUT/'combined-footage.png'))
    page.goto(f'{BASE}/#/render?project={PID}&layer=composite');page.wait_for_function('window.__typeset')
    pixels=page.evaluate('''async()=>{const api=window.__typeset;await api.ready;const c=document.querySelector('#stage'),result=[];
        for(const t of [5.5,7.5]){await api.renderFrame(t*24);result.push([...c.getContext('2d').getImageData(100,100,1,1).data]);}return result;}''')
    assert pixels[0][2]>pixels[0][0]*2 and pixels[1][0]>pixels[0][0]*1.5,pixels
    assert not errors,errors
    report=dict(checks=34,currentPixel=before,candidatePixel=candidate,run=runs[0],remoteRun=runs[-1],independentFootage=True,splitTrimUndo=True,repeatedSourcePreview=True,
                originalCutPreserved=True,saveReload=True,exportPixels=pixels,consoleErrors=errors)
    (OUT/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    browser.close()
