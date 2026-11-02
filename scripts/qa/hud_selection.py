"""Real pointer marquee selection, shared styling, and shot-bound HUD rendering. All API writes intercepted."""
import base64
import copy
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

OUT=Path('outputs/qa/hud-selection');OUT.mkdir(parents=True,exist_ok=True)
p=json.loads(Path('apps/web/public/sample/project.json').read_text())
p.update(id='hud-selection-check',name='HUD selection check',duration=10,fps=24,width=640,height=360,
         media={},analysis={},shots=[],layers=[],assets=[],surfaces=[],lineMeta={},look={'id':'hud'},grade=None,
         words=[dict(id=id,lineId=id,text=text,start=a,end=b,placement='overlay',preset='none')
                for id,text,a,b in [('a','FIRST',1,2),('b','SECOND',3,4),('c','LATER',6,7),('d','OVERLAP',3.5,4.5)]])
saved=[];errors=[];checks=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda e:errors.append(str(e)))
    def api(route):
        req=route.request;path=urlsplit(req.url).path
        if path=='/api/projects/'+p['id']:
            if req.method=='PUT':saved.append(req.post_data_json)
            route.fulfill(json=saved[-1] if saved else p)
        elif path=='/api/projects':route.fulfill(json=[p])
        elif path=='/api/jobs':route.fulfill(json=[])
        elif req.method not in ('GET','HEAD','OPTIONS'):route.abort()
        else:route.fulfill(status=404,json={})
    page.route('**/api/**',api)
    page.goto('http://127.0.0.1:5174/#/studio?project='+p['id'])
    page.wait_for_selector('.tl-region')
    expect(page.get_by_role('button',name='Play',exact=True)).to_be_enabled()
    def selected():return page.locator('.tl-line.sel').evaluate_all('(els)=>els.map(e=>e.dataset.lineId).sort()')
    def box(id):return page.locator(f'.tl-line[data-line-id="{id}"] .tl-region').bounding_box()
    def marquee(x0,y0,x1,y1,add=False,cancel=False):
        if add:page.keyboard.down('Shift')
        page.mouse.move(x0,y0);page.mouse.down();page.mouse.move(x1,y1,steps=12)
        if cancel:page.locator('.tl-scroll').dispatch_event('pointercancel',{'pointerId':1})
        page.mouse.up()
        if add:page.keyboard.up('Shift')
    body=page.locator('.tl-track .tl-body').bounding_box();pps=body['width']/10
    marquee(body['x']+.5*pps,body['y']+1,body['x']+5*pps,body['y']+body['height']-1)
    assert selected()==['a','b','d'],selected()
    expect(page.locator('.group-insp')).to_be_visible();checks.append('marquee across packed text rows')
    assert page.locator('.tl-marquee').count()==0
    color=page.locator('.group-insp .csw input[type=color]').first
    color.fill('#0000ff');page.wait_for_timeout(900)
    page.get_by_role('button',name='Save project',exact=True).click() if page.get_by_role('button',name='Save project',exact=True).count() else page.keyboard.press('Meta+s')
    page.wait_for_timeout(600)
    assert saved and all(saved[-1]['lineMeta'][id]['fill']=='#0000ff' for id in ['a','b','d']),saved[-1] if saved else None
    assert not saved[-1]['lineMeta'].get('c',{}).get('fill');assert saved[-1]['words']==p['words']
    checks.append('shared color changes only boxed clips; timing unchanged')
    page.get_by_role('radio',name='Caption',exact=True).click();page.wait_for_timeout(800);page.keyboard.press('Meta+s');page.wait_for_timeout(400)
    assert all(saved[-1]['lineMeta'][id]['appearance']['layout']=='line' for id in ['a','b','d'])
    assert not saved[-1]['lineMeta'].get('c',{}).get('appearance')
    page.keyboard.press('Meta+z');page.wait_for_timeout(800);page.keyboard.press('Meta+s');page.wait_for_timeout(400)
    assert all(not saved[-1]['lineMeta'][id].get('appearance') for id in ['a','b','d']);checks.append('shared role and undo preserve selection and color')
    body=page.locator('.tl-track .tl-body').bounding_box();pps=body['width']/10
    c=box('c');marquee(body['x']+5.5*pps,body['y']+1,c['x']+c['width']+8,c['y']+c['height']-1,add=True)
    assert selected()==['a','b','c','d'],selected();checks.append('shift marquee adds clips')
    page.locator('.word-chip[data-word-id="b"]').click(modifiers=['Shift'])
    assert selected()==['a','c','d'],selected();checks.append('shift click toggles a text clip')
    a=box('a');body=page.locator('.tl-track .tl-body').bounding_box();pps=body['width']/10
    marquee(body['x']+.5*pps,body['y']+1,a['x']+a['width']+5,a['y']+a['height']-1,cancel=True)
    assert selected()==['a','c','d'],selected();checks.append('cancel restores selection')
    # Color picker emits valid hex. Check its actual rendered ink + HUD strokes across saturated corners.
    colors=page.evaluate('''async p=>{const {StageRenderer}=await import('/src/renderer.ts');const results=[];
      for(const color of ['#0000ff','#ff0000','#8000ff','#000000','#0000ff80']){
        const q=structuredClone(p);q.words=q.words.slice(0,1);q.look={id:'hud',overrides:{palette:{text:color,accent:color}}};q.lineMeta={};
        const r=new StageRenderer(q);await r.load('text');const c=document.createElement('canvas');await r.render(c,36,'text');
        const unit=r.units(c.getContext('2d'))[0];results.push({color,ink:unit.metrics[0].style.fill});r.dispose();
      }return results;}''',p)
    assert all(c['color']==c['ink'] for c in colors),colors;checks.append('saturated and translucent HUD colors never switch to white')
    page.screenshot(path=str(OUT/'marquee-selection.png'))
    # Real So I Die head data. Rendering is read-only; keep the browser fixture and intercept all writes.
    live=json.loads(Path('data/projects/48f2389d-1d2e-42ff-af86-f90b4d8c4600/project.json').read_text())
    heads=page.evaluate('''async p=>{const {StageRenderer}=await import('/src/renderer.ts');const {headSourceAt,sampleHead}=await import('/src/heads.ts');
      const r=new StageRenderer(p);r.draftMedia=true;await r.load();const checks=[];
      for(const t of [2,5,9,12,15,18,21,25]){const h=r.head(t),src=headSourceAt(p,t),detected=src&&sampleHead(r.headTracks.get(src.path),src.time);checks.push({t,source:src?.path,state:h.state,detected:!!detected,x:h.point.cx,y:h.point.cy});}
      const c=document.createElement('canvas');await r.render(c,Math.round(9.8*p.fps));const png=c.toDataURL('image/png');
      const gap=r.head(100).state;r.dispose();return {checks,png,gap};}''',live)
    # The live cut and its source trims change while other agents edit. Compare with the current
    # source-time detections instead of assuming the first shot still has no visible face at 2s.
    assert all((h['state']=='tracked')==h['detected'] for h in heads['checks']),heads['checks']
    assert any(h['state']=='tracked' for h in heads['checks']);assert heads['gap']=='none'
    assert len({h['source'] for h in heads['checks']})>=6
    (OUT/'so-i-die-hud.png').write_bytes(base64.b64decode(heads.pop('png').split(',')[1]));checks.append('So I Die tracking matches the current visible-shot detections; no head outside footage')
    # Automatic head analysis must keep a text edit made while the job is running.
    auto=copy.deepcopy(p);auto.update(id='hud-auto-check',assets=[dict(id='photo',kind='image',path='media/photo.png',width=2,height=2)],
                                    layers=[dict(id='photo',kind='media',assetId='photo',start=0,**{'in':0},out=10)])
    auto_state=copy.deepcopy(auto);requests=[];finish=[False];auto_saves=[]
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aGf8AAAAASUVORK5CYII=')
    page2=browser.new_page(viewport={'width':1440,'height':1000})
    page2.on('pageerror',lambda e:errors.append(str(e)))
    def auto_api(route):
        req=route.request;path=urlsplit(req.url).path
        if path=='/api/projects/'+auto['id']:
            if req.method=='PUT':auto_saves.append(req.post_data_json)
            route.fulfill(json=auto_state)
        elif path=='/api/projects':route.fulfill(json=[auto])
        elif path=='/api/jobs':route.fulfill(json=[])
        elif path.endswith('/analyze/heads'):
            requests.append(req.post_data_json)
            route.fulfill(json=dict(id='head-check',kind='heads',status='queued',projectId=auto['id']))
        elif path=='/api/jobs/head-check':
            if finish[0]:auto_state['analysis']={'headTracks':{'media/photo.png':'analysis/heads.json'}}
            route.fulfill(json=dict(id='head-check',kind='heads',status='done' if finish[0] else 'running',projectId=auto['id']))
        elif req.method not in ('GET','HEAD','OPTIONS'):route.abort()
        else:route.fulfill(status=404,json={})
    page2.route('**/api/**',auto_api)
    page2.route('**/files/projects/hud-auto-check/media/photo.png',lambda route:route.fulfill(body=png,content_type='image/png'))
    page2.route('**/files/projects/hud-auto-check/analysis/heads.json',lambda route:route.fulfill(json=dict(fps=12,frames=1,tracks=[dict(id='person0',label='head',frames=[dict(f=0,cx=.4,cy=.3,bbox=[.2,.1,.4,.5])])])))
    page2.goto('http://127.0.0.1:5174/#/studio?project='+auto['id'])
    page2.wait_for_selector('.word-chip')
    page2.locator('.word-chip[data-word-id="a"]').click()
    expect(page2.get_by_role('button',name='Tracking…',exact=True)).to_be_visible()
    page2.get_by_role('textbox',name='Word text',exact=True).fill('EDITED DURING TRACKING')
    finish[0]=True
    expect(page2.get_by_role('button',name='Track head',exact=True)).to_be_enabled(timeout=15000)
    expect(page2.get_by_role('textbox',name='Word text',exact=True)).to_have_value('EDITED DURING TRACKING')
    page2.wait_for_timeout(1500);assert len(requests)==1,requests
    checks.append('HUD automatically tracks missing sources once and preserves edits made during the job')
    page2.close()
    from hud_pointer_checks import check_hud_pointer
    checks.extend(check_hud_pointer(browser,p,OUT))
    assert not errors,errors
    (OUT/'report.json').write_text(json.dumps(dict(checks=checks,colors=colors,heads=heads,errors=errors),indent=2))
    print(json.dumps(dict(checks=checks,heads=heads,errors=errors),indent=2))
    browser.close()
