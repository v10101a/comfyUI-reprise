"""HUD attachment drag and independent marker controls on an isolated project."""
import copy
import json
from urllib.parse import urlsplit

from playwright.sync_api import expect


def check_hud_pointer(browser, project, out):
    p=copy.deepcopy(project)
    p.update(id='hud-pointer-check',name='HUD pointer check',duration=8,media={},analysis={'headTracks':{'media/shot.mp4':'analysis/heads.json'}},
             assets=[dict(id='video',kind='video',path='media/shot.mp4',width=1280,height=720,duration=8)],
             layers=[dict(id='shot',kind='media',assetId='video',start=0,**{'in':0},out=8),dict(id='text',kind='text',which='front')],
             look={'id':'hud','overrides':{'optics':{'glow':0,'chroma':0},'raster':None}},lineMeta={},
             words=[dict(id='a',lineId='a',text='TRACK ME',start=.2,end=7.5,placement='overlay',preset='none'),
                    dict(id='b',lineId='b',text='NEXT',start=7.6,end=8,placement='overlay',preset='none')])
    tracks=dict(fps=12,frames=96,tracks=[dict(id='person0',label='head',frames=[dict(f=f,bbox=[.3+f*.001,.2+f*.0005,.25+f*.001,.45+f*.0005],
                       cx=.425+f*.0015,cy=.3575+f*.000675) for f in range(96)])])
    state=copy.deepcopy(p);saves=[];errors=[];checks=[]
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda e:errors.append(str(e)))
    def api(route):
        nonlocal state
        req=route.request;path=urlsplit(req.url).path
        if path=='/api/projects/'+p['id']:
            if req.method=='PUT':state=req.post_data_json;saves.append(copy.deepcopy(state))
            route.fulfill(json=state)
        elif path=='/api/projects':route.fulfill(json=[p])
        elif path=='/api/jobs':route.fulfill(json=[])
        elif path=='/api/health':route.fulfill(json={'comfyui':False})
        elif req.method not in ('GET','HEAD','OPTIONS'):route.abort()
        else:route.fulfill(status=404,json={})
    page.route('**/api/**',api)
    page.route('**/files/projects/hud-pointer-check/analysis/heads.json',lambda route:route.fulfill(json=tracks))
    page.route('**/files/projects/hud-pointer-check/media/shot.mp4',lambda route:route.fulfill(path='apps/web/public/sample/sample.mp4',content_type='video/mp4'))
    page.goto('http://127.0.0.1:5174/#/studio?project='+p['id'])
    page.locator('.word-chip[data-word-id="a"]').click()
    hit=page.get_by_role('button',name='Move HUD tracking point',exact=True)
    expect(hit).to_be_visible()
    def center():
        b=hit.bounding_box();return b['x']+b['width']/2,b['y']+b['height']/2
    def save():
        page.get_by_role('button',name='Save project',exact=True).click() if page.get_by_role('button',name='Save project',exact=True).count() else page.wait_for_timeout(1600)
        page.wait_for_timeout(300)
        assert saves
        return saves[-1]
    def drag(dx,dy,cancel=False):
        x,y=center();page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+dx,y+dy,steps=12)
        if cancel:hit.dispatch_event('pointercancel',{'pointerId':1})
        page.mouse.up()
    before=center();label=page.locator('.g-line.sel .g-box').get_attribute('points')
    drag(35,25);after=center()
    assert abs(after[0]-before[0]-35)<2 and abs(after[1]-before[1]-25)<2,(before,after)
    assert page.locator('.g-line.sel .g-box').get_attribute('points')==label
    saved=save();point=copy.deepcopy(saved['lineMeta']['a']['hud']['point'])
    assert saved['words']==p['words'];checks.append('dragging the dot changes only head-relative attachment; label and timing stay fixed')
    page.keyboard.press('Meta+z');page.wait_for_timeout(300);assert max(abs(a-b) for a,b in zip(center(),before))<2
    page.keyboard.press('Meta+Shift+z');page.wait_for_timeout(300);assert max(abs(a-b) for a,b in zip(center(),after))<2
    checks.append('one undo and redo restore the whole attachment gesture')
    drag(-20,18,cancel=True);assert save()['lineMeta']['a']['hud']['point']==point
    checks.append('pointer cancellation restores the previous attachment')
    ruler=page.locator('.tl-ruler').bounding_box();page.mouse.click(ruler['x']+ruler['width']*.5,ruler['y']+ruler['height']*.75)
    page.wait_for_timeout(300);later=center();assert abs(later[0]-after[0])>20
    assert save()['lineMeta']['a']['hud']['point']==point;checks.append('attachment follows movement and changing head size when seeking')
    hit.focus();old=center();label_at_nudge=page.locator('.g-line.sel .g-box').get_attribute('points');page.keyboard.press('ArrowRight');page.wait_for_timeout(150)
    assert abs(center()[0]-old[0]-1)<.2,(old,center())
    assert page.locator('.g-line.sel .g-box').get_attribute('points')==label_at_nudge
    page.keyboard.press('Meta+z');page.wait_for_timeout(200);assert max(abs(a-b) for a,b in zip(center(),old))<.2
    checks.append('keyboard nudges move the attachment, not the label or playhead')
    page.get_by_label('Dot color',exact=True).fill('#ff0000')
    page.get_by_label('Connector color',exact=True).fill('#0000ff')
    saved=save();assert saved['lineMeta']['a']['hud']['dotColor']=='#ff0000';assert saved['lineMeta']['a']['hud']['connectorColor']=='#0000ff'
    assert saved['words']==p['words'];checks.append('dot and connector colors are independent of text')
    pixels=page.evaluate('''async p=>{const {StageRenderer}=await import('/src/renderer.ts');const out=[];
      for(const [dot,connector] of [[true,true],[false,true],[true,false],[false,false]]){
        const q=structuredClone(p);q.lineMeta.a.hud={...q.lineMeta.a.hud,dot,connector};const r=new StageRenderer(q);await r.load('text');
        const c=document.createElement('canvas');await r.render(c,96,'text');const data=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
        let red=0,blue=0;for(let i=0;i<data.length;i+=4){if(data[i+3]<80)continue;if(data[i]>150&&data[i+1]<60&&data[i+2]<60)red++;
          if(data[i+2]>150&&data[i]<60&&data[i+1]<60)blue++;}out.push({dot,connector,red,blue});r.dispose();}return out;}''',saved)
    for r in pixels:
        assert (r['red']>0)==r['dot'] and (r['blue']>0)==r['connector'],pixels
    checks.append('actual text export pixels verify all four dot/connector visibility combinations')
    page.get_by_role('checkbox',name='Dot',exact=True).uncheck()
    page.get_by_role('checkbox',name='Connector line',exact=True).uncheck()
    saved=save();assert saved['lineMeta']['a']['hud']['dot'] is False and saved['lineMeta']['a']['hud']['connector'] is False
    page.reload();page.locator('.word-chip[data-word-id="a"]').click();expect(hit).to_be_visible()
    expect(page.get_by_role('checkbox',name='Dot',exact=True)).not_to_be_checked()
    expect(page.get_by_role('checkbox',name='Connector line',exact=True)).not_to_be_checked()
    assert page.get_by_label('Dot color',exact=True).input_value()=='#ff0000'
    assert state['lineMeta']['a']['hud']['point']==point
    page.get_by_role('button',name='Reset point',exact=True).click();saved=save()
    assert not saved['lineMeta']['a']['hud'].get('point');assert saved['lineMeta']['a']['hud']['dotColor']=='#ff0000'
    checks.append('attachment, colors and visibility persist after reload; reset changes only the point')
    page.locator('.word-chip[data-word-id="b"]').click(modifiers=['Shift'])
    page.get_by_role('checkbox',name='Dot',exact=True).check()
    page.get_by_label('Dot color',exact=True).fill('#00ff00');saved=save()
    assert all(saved['lineMeta'][id]['hud']['dotColor']=='#00ff00' and saved['lineMeta'][id]['hud']['dot'] for id in ['a','b'])
    checks.append('multi-selection applies the same pointer settings to selected HUD clips')
    page.screenshot(path=str(out/'pointer-controls.png'))
    assert not errors,errors
    (out/'pointer-report.json').write_text(json.dumps(dict(checks=checks,pixels=pixels,point=point,errors=errors),indent=2))
    page.close();return checks
