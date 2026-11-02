"""Timing edit/restore pixel regression and scoped reset. All API writes are intercepted."""
import copy
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/progress/animation-timing'
OUT.mkdir(parents=True,exist_ok=True)
p=json.loads((ROOT/'apps/web/public/sample/project.json').read_text())
p.update(id='animation-timing-check',name='Animation timing check',width=640,height=360,duration=4,fps=24,media={},analysis={},shots=[],layers=[],assets=[],timing=None,grade=None,
    look={'id':'hud','overrides':{'layout':'line','optics':{'glow':0,'chroma':0}}},
    surfaces=[{'id':'wall-1','corners':[[.1,.2],[.6,.15],[.62,.8],[.08,.9]],'material':'flat','status':'drawn','keyFrame':0}],
    words=[{'id':str(i),'lineId':'wall','text':text,'start':start,'end':end,'placement':'surface','surfaceId':'wall-1','preset':'pop'} for i,(text,start,end) in enumerate([('so',.3,.8),("I'll",.8,1.5),('die',1.5,3.8)])],
    lineMeta={'wall':{'u':.02,'v':-.1,'scale':1.16,'appearance':{'font':'Space Mono'}}})
state=copy.deepcopy(p);errors=[];saves=[];checks=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda e:errors.append(str(e)))
    def api(route):
        global state
        req=route.request;path=urlsplit(req.url).path
        if path=='/api/projects/'+p['id']:
            if req.method=='PUT':state=req.post_data_json;saves.append(copy.deepcopy(state))
            route.fulfill(json=state)
        elif path=='/api/projects':route.fulfill(json=[state])
        elif path=='/api/health':route.fulfill(json={'comfyui':False})
        elif path in ('/api/jobs','/api/looks/saved','/api/workflows'):route.fulfill(json=[])
        else:route.fulfill(json={})
    page.route('**/api/**',api)
    page.goto('http://127.0.0.1:5174/#/studio?project='+p['id'])
    page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    results=page.evaluate('''async p=>{
      const {StageRenderer,loadFonts}=await import('/src/renderer.ts');
      const {setLookParam,setLineMeta,clearLineAnimation,animOf,lookOf}=await import('/src/looks.ts');
      await loadFonts();const r=new StageRenderer(p),c=document.createElement('canvas'),checks=[];
      async function pixels(q,frame){r.project=q;await r.render(c,frame,'text');return c.toDataURL();}
      const restored=setLookParam(setLookParam(p,'in',.7),'in',animOf(lookOf(p)).in);
      for(const frame of [8,12,20,36,42,60,80]){
        const baseline=await pixels(p,frame);await pixels(setLookParam(p,'in',1.2),frame);
        checks.push({name:'default restore frame '+frame,ok:await pixels(restored,frame)===baseline});
        const cut={...p,look:{...p.look,overrides:{...p.look.overrides,enter:'cut'}}};
        checks.push({name:'zero is a cursor-free cut frame '+frame,ok:await pixels(setLineMeta(p,'wall',{animIn:0}),frame)===await pixels(cut,frame)});
      }
      const cut={...p,look:{...p.look,overrides:{...p.look.overrides,enter:'cut'}}};
      checks.push({name:'explicit duration finishes the cursor',ok:await pixels(setLineMeta(p,'wall',{animIn:.6}),51)===await pixels(cut,51)});
      const edited=setLineMeta(p,'wall',{animIn:2,animOut:.5});
      checks.push({name:'clip reset restores original rendered frame',ok:await pixels(clearLineAnimation(edited,['wall']),42)===await pixels(p,42)});
      // Once a short word has revealed its letters, a wall render must match the
      // same lettering without animation, even while its In interval is running.
      // Previously a bright block remained beside EACH word during this interval.
      for(const material of ['paint','flat','neon']){
        const wall={...p,words:[{...p.words[0],end:3.8}],surfaces:p.surfaces.map(s=>({...s,material})),
          look:{...p.look,overrides:{...p.look.overrides,optics:{glow:.5}}}};
        const cut={...wall,look:{...wall.look,overrides:{...wall.look.overrides,enter:'cut'}}};
        checks.push({name:material+' wall has only revealed letters, no extra cursor block',ok:await pixels(setLineMeta(wall,'wall',{animIn:1}),25)===await pixels(cut,25)});
        checks.push({name:material+' wall respects slower clip timing',ok:await pixels(setLineMeta(wall,'wall',{animIn:1}),10)!==await pixels(setLineMeta(wall,'wall',{animIn:.2}),10)});
        checks.push({name:material+' wall respects slower project timing',ok:await pixels(setLookParam(wall,'in',1),10)!==await pixels(setLookParam(wall,'in',.2),10)});
        const explicit=setLineMeta(wall,'wall',{animIn:1});
        checks.push({name:material+' clip timing wins until reset',ok:await pixels(setLookParam(explicit,'in',.2),10)===await pixels(explicit,10)&&await pixels(clearLineAnimation(setLookParam(explicit,'in',.2),['wall']),10)===await pixels(setLookParam(wall,'in',.2),10)});
      }
      const hud={...p,words:[{...p.words[0],placement:'anchor',preset:'hud',end:3.8}]};
      const hudCut={...hud,look:{...hud.look,overrides:{...hud.look.overrides,enter:'cut'}}};
      checks.push({name:'head-attached HUD retains its typing cursor',ok:await pixels(setLineMeta(hud,'wall',{animIn:1}),25)!==await pixels(hudCut,25)});
      // Exercise warm caches through a full edit -> restore cycle too.
      for(const value of [0,3,.6,null]){const q=setLineMeta(p,'wall',{animIn:value});const warm=await pixels(q,43);
        const fresh=new StageRenderer(q),fc=document.createElement('canvas');await fresh.render(fc,43,'text');
        checks.push({name:'warm/fresh parity '+value,ok:warm===fc.toDataURL()});fresh.dispose();}
      r.dispose();return checks;
    }''',p)
    assert all(x['ok'] for x in results),results
    checks.extend(x['name'] for x in results)
    page.locator('.scene-text-button').click()
    page.locator('.lp-details > summary').click()
    expect(page.get_by_text('Default timing',exact=True)).to_be_visible()
    checks.append('look inspector identifies project timing defaults')
    page.locator('.word-chip[data-word-id="2"]').click()
    page.get_by_text('Position & motion',exact=True).click()
    page.get_by_role('spinbutton',name='In',exact=True).fill('0.6')
    page.get_by_role('spinbutton',name='Out',exact=True).fill('0.5')
    page.get_by_role('spinbutton',name='Out',exact=True).blur()
    expect(page.get_by_role('button',name='Reset animation timing')).to_be_visible()
    expect(page.get_by_role('button',name='Reset animation timing')).to_have_text('Use project timing')
    expect(page.get_by_role('spinbutton',name='In',exact=True).locator('..')).to_have_attribute('title','Entrance, s · 0 = none · clip override')
    page.wait_for_timeout(1800)
    assert saves and saves[-1]['lineMeta']['wall']['animIn']==.6
    assert saves[-1]['words']==p['words']
    checks.append('timing edits preserve wall placement and word times')
    page.get_by_role('button',name='Reset animation timing').click()
    expect(page.get_by_role('button',name='Reset animation timing')).to_have_count(0)
    expect(page.get_by_role('spinbutton',name='In',exact=True)).to_have_value('0.3')
    page.wait_for_timeout(1800)
    assert saves[-1]['lineMeta']==p['lineMeta']
    assert saves[-1]['words']==p['words']
    checks.append('timing reset preserves font, wall transform and all authored words')
    page.keyboard.press('Meta+z')
    expect(page.get_by_role('spinbutton',name='In',exact=True)).to_have_value('0.6')
    expect(page.get_by_role('spinbutton',name='Out',exact=True)).to_have_value('0.5')
    checks.append('timing reset is undoable')
    page.screenshot(path=str(OUT/'timing-reset.png'))
    assert not errors,errors
    result={'passed':len(checks),'checks':checks,'errors':errors,'realProjectWrites':0}
    (OUT/'checks.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    browser.close()
