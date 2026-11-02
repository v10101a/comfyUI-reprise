"""Timeline duration and footage drops, using isolated API fixtures and actual video pixels."""
import base64,copy,json,re,subprocess,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

PID='timeline-media-qa';OUT=Path('outputs/progress/timeline-media');OUT.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:5174'
saved=dict(version=1,id=PID,name='Timeline footage check',width=160,height=96,fps=24,duration=3,media={},analysis={},shots=[],surfaces=[],grade=None,words=[],
    style=dict(fontFamily='Inter',fontWeight=700,fontSize=.1,fill='#ffffff',align='center'),
    assets=[dict(id='a',kind='video',path='media/source.mp4',name='First shot',duration=4,width=64,height=64,fps=24),
            dict(id='b',kind='video',path='media/second.mp4',name='Second shot',duration=2,width=64,height=64,fps=24)],
    layers=[dict(id='first',kind='media',assetId='a',name='First shot',start=0,**{'in':0},out=3,keys=[dict(t=0,opacity=1)])])
initial=copy.deepcopy(saved);uploads=[];errors=[]
with tempfile.TemporaryDirectory() as tmp,sync_playwright() as pw:
    path=Path(tmp)/'source.mp4'
    subprocess.run(['/opt/homebrew/bin/ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=red:s=64x64:r=24:d=4','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
    video=path.read_bytes()
    browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport=dict(width=1440,height=1000));page.on('pageerror',lambda e:errors.append(str(e)))
    def api(route):
        global saved
        req=route.request;url=req.url.split('/api/',1)[-1].split('?',1)[0]
        if url==f'projects/{PID}':
            if req.method=='PUT':saved=req.post_data_json
            return route.fulfill(json=saved)
        if url=='projects':return route.fulfill(json=[saved])
        if url=='workflows' or url=='jobs':return route.fulfill(json=[])
        if url=='health':return route.fulfill(json=dict(comfyui=True))
        if url=='session':return route.fulfill(json=dict(projectId=PID))
        if url==f'projects/{PID}/assets':
            uploads.append(len(req.post_data_buffer or b''));n=len(uploads)
            return route.fulfill(json=dict(id=f'upload{n}',kind='video',path=f'media/upload{n}.mp4',name=f'Upload {n}',duration=2,width=64,height=64,fps=24))
        return route.fulfill(status=404,json=dict(detail='Disabled in isolated timeline QA'))
    def media(route):
        if '/proxy/' in route.request.url:return route.fulfill(status=404)
        match=re.match(r'bytes=(\d+)-(\d*)',route.request.headers.get('range',''));headers={'Accept-Ranges':'bytes'}
        if match:
            start=int(match[1]);end=min(len(video)-1,int(match[2]) if match[2] else len(video)-1);headers['Content-Range']=f'bytes {start}-{end}/{len(video)}'
            return route.fulfill(status=206,body=video[start:end+1],content_type='video/mp4',headers=headers)
        route.fulfill(body=video,content_type='video/mp4',headers=headers)
    page.route('**/api/**',api);page.route(f'**/files/projects/{PID}/media/**',media)
    def save():
        with page.expect_response(lambda r:r.request.method=='PUT' and f'projects/{PID}' in r.url):page.locator('.s-save').click()
    def empty_pixel(p,frame):
        return page.evaluate('''async ({p,frame})=>{const {StageRenderer}=await import('/src/renderer.ts');const r=new StageRenderer(p);await r.load();
          const c=document.createElement('canvas');await r.render(c,frame);const pixel=[...c.getContext('2d').getImageData(80,48,1,1).data];r.dispose();return pixel;}''',dict(p=p,frame=frame))
    page.goto(f'{BASE}/#/studio?project={PID}');page.wait_for_selector('.stage-wrap');page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    length=page.get_by_label('Timeline length in seconds');expect(length).to_have_value('3.00')
    page.get_by_role('button',name='Extend timeline by 5 seconds').click();expect(length).to_have_value('8.00');save()
    assert saved['layers']==initial['layers']
    gap=empty_pixel(saved,5*24);assert gap[3]==0,gap
    # Original footage also ends instead of holding forever when the edit gets longer.
    legacy=copy.deepcopy(saved);legacy.pop('layers');legacy['media']={'video':dict(path='media/source.mp4',duration=4,width=64,height=64,fps=24)}
    assert empty_pixel(legacy,5*24)[:3]==[36,41,35]
    legacy['layers']=[dict(id='plate',kind='plate')];assert empty_pixel(legacy,5*24)[:3]==[36,41,35]
    page.reload();expect(length).to_have_value('8.00')
    page.get_by_role('button',name='Media',exact=True).click()
    drop=page.locator('.tl-add-media .tl-body');box=drop.bounding_box()
    page.locator('.as-item').nth(1).drag_to(drop,target_position=dict(x=box['width']-2,y=14))
    expect(length).to_have_value('10.00');save()
    placed=copy.deepcopy(saved);new=saved['layers'][-1];assert (new['assetId'],new['start'],new['in'],new['out'])==('b',8,0,2),new
    page.keyboard.press('Meta+z');expect(length).to_have_value('8.00');expect(page.locator('.ly-lane')).to_have_count(1)
    page.keyboard.press('Meta+Shift+z');expect(length).to_have_value('10.00')
    # Native file drops use the upload route and preserve complete, consecutive clips.
    transfer=page.evaluate_handle('''encoded=>{const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));const dt=new DataTransfer();
      dt.items.add(new File([bytes],'third.mp4',{type:'video/mp4'}));dt.items.add(new File([bytes],'fourth.mp4',{type:'video/mp4'}));return dt;}''',base64.b64encode(video).decode())
    box=drop.bounding_box();event=dict(dataTransfer=transfer,clientX=box['x']+box['width']-2,clientY=box['y']+14)
    drop.dispatch_event('dragover',event);expect(page.locator('.tl-drop-marker')).to_be_visible();drop.dispatch_event('drop',event)
    expect(length).to_have_value('14.00');expect(page.locator('.ly-clip')).to_have_count(4);expect(page.locator('.ly-lane')).to_have_count(1);save()
    assert len(uploads)==2 and all(size>len(video) for size in uploads),uploads
    imported=[l for l in saved['layers'] if l['assetId'].startswith('upload')];assert [(l['start'],l['out']) for l in imported]==[(10,2),(12,2)]
    page.keyboard.press('Meta+z');expect(length).to_have_value('10.00');save();assert len(saved['assets'])==4,'Undo keeps uploaded files in the bin'
    page.keyboard.press('Meta+Shift+z');expect(length).to_have_value('14.00')
    # Extending an existing video stops at its source boundary.
    first=page.get_by_role('group',name='Visual clip: First shot',exact=True)
    first.click();media_length=page.get_by_label('Layer length in seconds');media_length.fill('20');media_length.press('Enter')
    expect(media_length).to_have_value('4.00');expect(length).to_have_value('14.00');save();assert saved['layers'][0]['out']==4
    # Moving the last clip past the edit grows duration in the same undo step.
    tail=page.get_by_role('group',name='Visual clip: Upload 2',exact=True)
    box=tail.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
    page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+65,y,steps=8);page.mouse.up();save()
    assert saved['duration']>14
    last=next(l for l in saved['layers'] if l['assetId']=='upload2');assert abs(saved['duration']-(last['start']+2))<1/24
    page.keyboard.press('Meta+z');expect(length).to_have_value('14.00');save()
    # A move into overlap is stable during the gesture, then separates by the composition stack.
    box=tail.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
    page.mouse.move(x,y);page.mouse.down();page.mouse.move(x-100,y,steps=8)
    expect(page.locator('.ly-lane')).to_have_count(1);page.mouse.up();expect(page.locator('.ly-lane')).to_have_count(2)
    upper=page.get_by_role('group',name='Visual clip: Upload 2',exact=True).bounding_box()['y']
    lower=page.get_by_role('group',name='Visual clip: Upload 1',exact=True).bounding_box()['y'];assert upper<lower
    page.keyboard.press('Meta+z');expect(page.locator('.ly-lane')).to_have_count(1)
    # Deleting or hiding one clip must not affect its neighbours in the shared row.
    tail.hover();tail.get_by_role('button',name='Hide layer: Upload 2',exact=True).click()
    expect(tail).to_have_class(re.compile(r'\boff\b'));assert not page.get_by_role('group',name='Visual clip: Upload 1',exact=True).evaluate('(e)=>e.classList.contains("off")')
    tail.get_by_role('button',name='Show layer: Upload 2',exact=True).click()
    tail.get_by_role('button',name='Delete layer: Upload 2',exact=True).click();expect(page.locator('.ly-clip')).to_have_count(3)
    page.keyboard.press('Meta+z');expect(page.locator('.ly-clip')).to_have_count(4);expect(page.locator('.ly-lane')).to_have_count(1);save()
    page.screenshot(path=str(OUT/'timeline.png'))
    # Render route uses the extended project frame count, including the gap and new clips.
    page.goto(f'{BASE}/#/render?project={PID}&layer=composite');page.wait_for_function('window.__typeset')
    rendered=page.evaluate('''async()=>{const api=window.__typeset;await api.ready;const c=document.querySelector('#stage');
      await api.renderFrame(5*24);const gap=[...c.getContext('2d').getImageData(80,48,1,1).data];
      await api.renderFrame(9*24);const shot=[...c.getContext('2d').getImageData(80,48,1,1).data];return {frames:api.frames,gap,shot};}''')
    assert rendered['frames']==14*24 and rendered['gap'][3]==0 and rendered['shot'][0]>200,rendered
    # The original-footage filmstrip also leaves the extended portion empty.
    saved=legacy;page.goto(f'{BASE}/#/studio?project={PID}')
    page.wait_for_function("(()=>{const c=document.querySelector('.tl-filmcanvas');return c&&c.getContext('2d').getImageData(10,10,1,1).data[3]>0})()")
    assert page.locator('.tl-filmcanvas').evaluate('(c)=>c.getContext("2d").getImageData(Math.floor(c.width*.8),10,1,1).data[3]')==0
    # Text rows precede visual rows and the original-footage strip, with audio at the bottom.
    saved['words']=[dict(id='caption',lineId='caption',text='caption',start=0,end=1,placement='overlay',preset='none')]
    saved['layers']=initial['layers'];page.reload();page.wait_for_selector('.ly-clip');page.wait_for_selector('.word-chip')
    order=page.evaluate('''()=>[...document.querySelectorAll('.tl-inner>.tl-row')].map(e=>e.className)''')
    text_at=next(i for i,c in enumerate(order) if 'grp-' in c);visual_at=next(i for i,c in enumerate(order) if 'ly-lane' in c)
    film_at=next(i for i,c in enumerate(order) if 'tl-film' in c);audio_at=next(i for i,c in enumerate(order) if 'tl-audio' in c)
    assert text_at<visual_at<film_at<audio_at,order
    page.screenshot(path=str(OUT/'text-above-visuals.png'))
    # Prepending song time keeps original footage, visual clips and words aligned, with a true empty lead-in.
    saved=page.evaluate('''async p=>{const {fitSongRange}=await import('/src/studio/duration.ts');
      return fitSongRange(p,{in:3,out:13,offset:-2},30).project;}''',saved)
    assert saved['timing']['sceneOffset']==2 and saved['duration']==10
    assert saved['layers'][0]['start']==2 and saved['words'][0]['start']==2
    assert empty_pixel(saved,24)[3]==0
    assert empty_pixel(saved,3*24)[0]>200
    original_only=copy.deepcopy(saved);original_only.pop('layers');original_only['words']=[]
    assert empty_pixel(original_only,24)[:3]==[36,41,35]
    assert empty_pixel(original_only,3*24)[0]>200
    assert empty_pixel(original_only,7*24)[:3]==[36,41,35]
    shorter=page.evaluate('''async p=>{const {fitSongRange}=await import('/src/studio/duration.ts');
      return fitSongRange(p,{in:3,out:4,offset:0},30,false).project;}''',saved)
    assert shorter['duration']==6 and shorter['layers']==saved['layers'] and shorter['words']==saved['words']
    assert empty_pixel(shorter,3*24)[0]>200
    page.reload()
    page.wait_for_function("(()=>{const c=document.querySelector('.tl-filmcanvas');return c&&c.getContext('2d').getImageData(Math.floor(c.width*.3),10,1,1).data[3]>0})()")
    assert page.locator('.tl-filmcanvas').evaluate('(c)=>c.getContext("2d").getImageData(10,10,1,1).data[3]')==0
    page.screenshot(path=str(OUT/'prepended-footage.png'))
    assert not errors,errors
    report=dict(emptyTime=True,assetDrop=True,fileUploads=len(uploads),consecutiveClips=True,fullSourceDuration=True,undoKeepsAssets=True,sourceLimitedTrim=True,moveExpandsTimeline=True,saveReload=True,filmstripEndsAtSource=True,sharedVisualRows=True,overlapStackOrder=True,stableDuringDrag=True,perClipDeleteUndo=True,textAboveVisuals=True,prependPreservesVisuals=True,shrinkKeepsLongestClip=True,render=rendered,consoleErrors=errors)
    (OUT/'checks.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));browser.close()
