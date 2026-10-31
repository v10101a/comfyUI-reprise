"""Brief P0 #2 acceptance: under a hero look, each line has one huge hero word (behind when a matte exists) and
satellites overlap the subject (occupancy > 5% of the box) in ≤10% of the line's frames.
Usage: server/.venv/bin/python apps/web/scripts/check_hero_acceptance.py <project-id> [look]"""
import asyncio, json, os, sys
from playwright.async_api import async_playwright
BASE = os.environ.get('TYPESET_WEB_URL', 'http://127.0.0.1:5174')
PID = sys.argv[1]; LOOK = sys.argv[2] if len(sys.argv) > 2 else 'red-glow'
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page()
        await pg.goto(f'{BASE}/#/render?project={PID}&layer=text&server=http://127.0.0.1:8787')
        await pg.wait_for_function('window.__typeset !== undefined'); await pg.evaluate('window.__typeset.ready')
        res = await pg.evaluate('''async ([pid,look])=>{
          const {StageRenderer}=await import('/src/renderer.ts');const {getProject}=await import('/src/api.ts');
          const p=await getProject(pid,'http://127.0.0.1:8787');p.look={id:look};
          const r=new StageRenderer(p,'http://127.0.0.1:8787');await r.load('text');
          const ctx=document.createElement('canvas').getContext('2d');const units=r.units(ctx);const plan=r.layout(ctx);const occ=r.occ();
          const out=[];
          for(const u of units){if(u.role!=='hero'&&u.role!=='sat')continue;const pl=plan.get(u.key);if(!pl)continue;
            const w=Math.min(1,u.total*pl.scale/p.width),h=u.height*pl.scale/p.height;let hit=0,n=0;
            const f0=Math.round(u.start*p.fps),f1=Math.round(u.end*p.fps)-1;
            for(let f=f0;f<=f1;f++){const g=occ.at(f);if(!g)continue;n++;let s=0,c=0;
              for(let r2=0;r2<g.rows;r2++)for(let k=0;k<g.cols;k++){const x=(k+.5)/g.cols,y=(r2+.5)/g.rows;if(Math.abs(x-pl.cx)<=w/2&&Math.abs(y-pl.cy)<=h/2){s+=g.data[r2*g.cols+k];c++;}}
              if(c&&s/c>.05)hit++;}
            out.push({role:u.role,text:u.metrics.map(m=>m.text).join(' '),placement:u.placement,sizeOfMin:+(u.size/Math.min(p.width,p.height)).toFixed(3),frames:n,overlapFrac:n?+(hit/n).toFixed(3):0,cx:+pl.cx.toFixed(2),cy:+pl.cy.toFixed(2)});}
          return out;}''', [PID, LOOK])
        ok = True
        for u in res:
            flag = ''
            if u['role'] == 'sat' and u['overlapFrac'] > .10: flag = '  <-- FAIL'; ok = False
            print(json.dumps(u) + flag)
        print('PASS' if ok else 'FAIL', 'hero acceptance', PID, LOOK)
        await b.close()
asyncio.run(main())
