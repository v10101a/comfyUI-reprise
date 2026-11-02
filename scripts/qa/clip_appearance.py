"""Exercise clip controls and the real browser renderer without saving any user project."""
import base64
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT = Path('outputs/progress/clip-appearance')
OUT.mkdir(parents=True, exist_ok=True)
PID = 'appearance-test'
BASE = os.environ.get('TYPESET_UI_URL', 'http://127.0.0.1:5174')
saved = dict(version=1, id=PID, name='Clip appearance test', width=640, height=360, fps=24,
             duration=5, media={}, analysis={}, shots=[], surfaces=[], grade=None,
             style=dict(fontFamily='Inter',fontWeight=700,fontSize=.1,fill='#ffffff',align='center'),
             look=dict(id='glyph'), lineMeta=dict(a=dict(hook=True),b=dict(hook=True)),
             words=[dict(id=k,lineId=k,text=text,start=0,end=4,placement='overlay',preset='none',
                         autoPlace=False,position=dict(x=.5,y=y)) for k,text,y in [('a','STAY',.3),('b','HERE',.7)]])
errors=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport=dict(width=1440,height=1050))
    page.on('pageerror',lambda e:errors.append(str(e)))
    def guard(route):
        global saved
        req=route.request
        path=req.url.split('/api/',1)[-1].split('?',1)[0]
        if path==f'projects/{PID}':
            if req.method=='PUT':saved=req.post_data_json
            route.fulfill(json=saved)
        elif path=='health':route.fulfill(json=dict(comfyui=True,remote=dict(comfyui=True)))
        elif path=='jobs':route.fulfill(json=[])
        else:route.fulfill(status=404,json=dict(detail='Disabled in appearance test'))
    page.route('**/api/**',guard)
    page.goto(f'{BASE}/#/studio?project={PID}')
    page.wait_for_selector('.stage-wrap')
    page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    page.locator('.word-chip[data-word-id="a"]').click()
    panel=page.locator('.clip-appearance')
    expect(panel.get_by_label('Font',exact=True)).to_have_value('IBM Plex Mono')
    panel.get_by_label('Font',exact=True).select_option('Anton')
    expect(panel.get_by_role('button',name='Reset Font to look')).to_be_visible()
    panel.get_by_text('Glyph settings',exact=True).click()
    panel.get_by_label('Glyph mask',exact=True).select_option('world')
    expect(panel.get_by_role('button',name='Reset Glyph mask to look')).to_be_visible()
    page.locator('.word-chip[data-word-id="b"]').click()
    expect(panel.get_by_label('Font',exact=True)).to_have_value('IBM Plex Mono')
    expect(panel.get_by_label('Glyph mask',exact=True)).to_have_value('subject')
    page.locator('.word-chip[data-word-id="a"]').click()
    expect(panel.get_by_label('Font',exact=True)).to_have_value('Anton')
    expect(panel.get_by_label('Glyph mask',exact=True)).to_have_value('world')
    page.screenshot(path=str(OUT/'inspector.png'))
    panel.get_by_role('button',name='Reset Glyph mask to look').click()
    expect(panel.get_by_label('Glyph mask',exact=True)).to_have_value('subject')
    panel.get_by_role('button',name='Use look',exact=True).click()
    expect(panel.get_by_label('Font',exact=True)).to_have_value('IBM Plex Mono')
    expect(panel.get_by_role('button',name='Use look',exact=True)).to_have_count(0)
    # Track selection applies the same controls to both clips and survives the actual save/load UI.
    page.locator('.grp-hooks .tl-head').click(position=dict(x=35,y=10))
    expect(page.locator('.group-insp')).to_be_visible()
    panel.get_by_label('Font',exact=True).select_option('Anton')
    panel.get_by_label('Glyph mask',exact=True).select_option('world')
    with page.expect_response(lambda r:r.request.method=='PUT' and f'projects/{PID}' in r.url):
        page.locator('.s-save').click()
    assert all(saved['lineMeta'][k]['appearance']['font']=='Anton' for k in ['a','b'])
    page.reload()
    page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    page.locator('.word-chip[data-word-id="b"]').click()
    expect(panel.get_by_label('Font',exact=True)).to_have_value('Anton')
    expect(panel.get_by_label('Glyph mask',exact=True)).to_have_value('world')
    results=page.evaluate('''async (fixture)=>{
      const {StageRenderer,loadFonts}=await import('/src/renderer.ts');
      const {setLineParam,setLineMeta,lineLookOf,lookOf}=await import('/src/looks.ts');
      await loadFonts();
      const assert=(v,msg)=>{if(!v)throw new Error(msg)};
      const canvas=()=>Object.assign(document.createElement('canvas'),{width:640,height:360});
      const env=canvas();env.getContext('2d').fillStyle='#ffffff';env.getContext('2d').fillRect(0,0,640,360);
      const matte=canvas();matte.getContext('2d').fillRect(0,0,320,360);
      const glyph=(p,t=1)=>{const c=canvas(),r=new StageRenderer(p);r.env=env;r.matte=matte;r.autoPlace=false;r.textPass(c.getContext('2d'),t,t*24,'all',false);return c};
      const count=(c)=>{const d=c.getContext('2d').getImageData(0,0,640,360).data;const n={leftRed:0,rightRed:0,leftBlue:0,rightBlue:0};
        for(let y=0;y<360;y++)for(let x=0;x<640;x++){const i=(y*640+x)*4;if(d[i+3]<32||(x>=304&&x<=336))continue;
          if(d[i]>d[i+2]*2&&d[i]>60)n[x<304?'leftRed':x>336?'rightRed':'ignored']++;
          if(d[i+2]>d[i]*2&&d[i+2]>60)n[x<304?'leftBlue':x>336?'rightBlue':'ignored']++;}return n;};
      let p=structuredClone(fixture);p.lineMeta={a:{hook:true},b:{hook:true}};p.look.overrides={optics:{glow:0,blur:0,chroma:0,motionBlur:0,lensWarp:0},fill:{region:'subject',backing:0,cell:.025}};
      p=setLineMeta(p,'a',{fill:'#ff0000'});p=setLineMeta(p,'b',{fill:'#0000ff'});
      p=setLineParam(p,['b'],'fill','world');const c=glyph(p),regions=count(c);
      assert(regions.leftRed>500&&regions.rightRed===0,'Person clip escaped its matte: '+JSON.stringify(regions));
      assert(regions.rightBlue>500&&regions.leftBlue===0,'Background clip invaded subject: '+JSON.stringify(regions));
      const red=glyph({...p,words:p.words.filter(w=>w.lineId==='a')},4.1);
      assert(count(red).leftRed>0,'Glyph fade-out was truncated');
      const plain=structuredClone(fixture);plain.look={id:'dreamy',overrides:{layout:'line',font:{hero:'Inter',body:'Inter'},optics:{glow:0,blur:0,chroma:0,motionBlur:0,lensWarp:0},raster:null}};
      plain.lineMeta={a:{hook:true},b:{hook:true}};
      const render=async p=>{const c=canvas(),r=new StageRenderer(p);r.autoPlace=false;await r.render(c,24,'text');return {c,r}};
      const before=await render(plain);let changed=setLineParam(plain,['a'],'font','Anton');changed=setLineMeta(changed,'a',{fill:'#ff0000'});
      const after=await render(changed);const us=after.r.units(after.c.getContext('2d'));
      assert(us.find(u=>u.lineId==='a').metrics[0].style.fontFamily==='Anton','Clip font lost to look');
      assert(us.find(u=>u.lineId==='b').metrics[0].style.fontFamily==='Inter','Sibling font changed');
      assert(us.find(u=>u.lineId==='a').metrics[0].style.fill==='#ff0000','Clip colour lost to look');
      const diff=(a,b,y0,y1)=>{const ad=a.getContext('2d').getImageData(0,y0,640,y1-y0).data,bd=b.getContext('2d').getImageData(0,y0,640,y1-y0).data;let n=0;for(let i=0;i<ad.length;i++)if(ad[i]!==bd[i])n++;return n;};
      assert(diff(before.c,after.c,0,180)>100,'Font and colour did not change actual pixels');
      assert(diff(before.c,after.c,180,360)===0,'Sibling pixels changed');
      const raster=await render(setLineParam(plain,['a'],'dots','square'));
      assert(diff(before.c,raster.c,0,180)>100,'Clip raster did not change pixels');
      assert(diff(before.c,raster.c,180,360)===0,'Clip raster changed sibling pixels');
      const blur=await render(setLineParam(plain,['a'],'soft',.8));
      assert(diff(before.c,blur.c,0,180)>100,'Clip blur did not change pixels');
      assert(diff(before.c,blur.c,180,360)===0,'Clip blur changed sibling pixels');
      const hud=setLineParam({...plain,words:plain.words.map(w=>({...w,placement:'anchor',preset:'hud'}))},['a'],'font','Anton');
      const hu=new StageRenderer(hud).units(canvas().getContext('2d'));assert(hu.find(u=>u.lineId==='a').metrics[0].style.fontFamily==='Anton','Anchored clip ignored font');
      return {regions,checks:9,glyph:c.toDataURL(),font:after.c.toDataURL(),raster:raster.c.toDataURL()};
    }''',saved)
    for key in ['glyph','font','raster']:
        (OUT/f'{key}.png').write_bytes(base64.b64decode(results.pop(key).split(',')[1]))
    # Current Studio and the shared scene-workspace inspector use the same look-specific controls.
    page.locator('.word-chip[data-word-id="a"]').click()
    panel.get_by_role('button',name='Use look',exact=True).click()
    controls=[]
    for name,global_label,clip_label in [('HUD','Readout color','Readout color'),('Neon','Flicker','Flicker'),('Stitch','Dots','Dots'),('Flat card','Padding','Padding'),('Glyph','Letter grid','Glyph mask')]:
        page.locator('.crumb-root').click()
        page.locator(f'.looks button.look-card[title^="{name} —"]').click()
        settings=page.locator('.lp-details')
        if not settings.evaluate('(el)=>el.open'):settings.locator('summary').click()
        expect(settings.get_by_label(global_label,exact=True)).to_be_visible()
        expect(settings.get_by_label('Layout',exact=True)).to_have_count(0)
        # Dots are the shared-effect exception; the surrounding style stays selected.
        dots=settings.get_by_label('Dots',exact=True)
        expect(dots).to_be_visible()
        dots.select_option('off')
        expect(settings.get_by_label('Dot size',exact=True)).to_have_count(0)
        dots.select_option('round')
        expect(settings.get_by_label('Dot size',exact=True)).to_be_visible()
        expect(settings.get_by_label('Dot gap',exact=True)).to_be_visible()
        if name!='Glyph':expect(settings.get_by_label('Letter grid',exact=True)).to_have_count(0)
        page.locator('.word-chip[data-word-id="a"]').click()
        details=panel.locator('.clip-more')
        if not details.evaluate('(el)=>el.open'):details.locator('summary').click()
        expect(panel.get_by_label(clip_label,exact=True)).to_be_visible()
        expect(panel.get_by_label('Layout',exact=True)).to_have_count(0)
        expect(page.locator('.insp .presets')).to_have_count(0)
        expect(panel.get_by_label('Dots',exact=True)).to_have_value('round')
        panel.get_by_label('Dots',exact=True).select_option('off')
        expect(panel.get_by_label('Dot size',exact=True)).to_have_count(0)
        page.locator('.word-chip[data-word-id="b"]').click()
        expect(panel.get_by_label('Dots',exact=True)).to_have_value('round')
        page.locator('.word-chip[data-word-id="a"]').click()
        expect(panel.get_by_label('Dots',exact=True)).to_have_value('off')
        panel.get_by_role('button',name='Reset Dots to look',exact=True).click()
        expect(panel.get_by_label('Dots',exact=True)).to_have_value('round')
        panel.get_by_label('Dots',exact=True).select_option('square')
        expect(panel.get_by_label('Dot size',exact=True)).to_be_visible()
        panel.get_by_role('button',name='Reset Dots to look',exact=True).click()
        if name!='Glyph':expect(panel.get_by_label('Glyph mask',exact=True)).to_have_count(0)
        controls.append(name)
    page.screenshot(path=str(OUT/'look-specific-controls.png'))
    # Saved clip appearance and old combinations remain renderer-compatible after narrowing the UI.
    with page.expect_response(lambda r:r.request.method=='PUT' and f'projects/{PID}' in r.url):
        page.locator('.s-save').click()
    assert saved['lineMeta']['b']['appearance']['font']=='Anton'
    assert saved['lineMeta']['b']['appearance']['fill']=='world'
    # Raw per-word animation presets remain available when no Look is selected.
    page.locator('.crumb-root').click()
    page.locator('.looks button.look-card[title^="Default —"]').click()
    page.locator('.word-chip[data-word-id="a"]').click()
    expect(page.locator('.insp .presets')).to_have_count(1)
    page.locator('.crumb-root').click()
    page.locator('.looks button.look-card[title^="Glyph —"]').click()
    with page.expect_response(lambda r:r.request.method=='PUT' and f'projects/{PID}' in r.url):
        page.locator('.s-save').click()
    assert not errors,errors
    results['look_controls']=controls
    (OUT/'results.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results))
    browser.close()
