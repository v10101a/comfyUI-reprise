"""Measure per-frame render cost of looks (P0b motion blur + chroma), sequential like an export.
Usage: server/.venv/bin/python apps/web/scripts/measure_optics.py [project-id] [frames]"""
import asyncio, json, os, sys
from playwright.async_api import async_playwright
BASE = os.environ.get('TYPESET_WEB_URL', 'http://127.0.0.1:5174')
PID = sys.argv[1] if len(sys.argv) > 1 else 'beeba9e1-9178-4f24-b9ce-9fb119bb33f6'
N = int(sys.argv[2]) if len(sys.argv) > 2 else 48
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page()
        await pg.goto(f'{BASE}/#/render?project={PID}&layer=composite&server=http://127.0.0.1:8787')
        await pg.wait_for_function('window.__typeset !== undefined'); await pg.evaluate('window.__typeset.ready')
        res = await pg.evaluate('''async ([pid,n])=>{
          const {StageRenderer}=await import('/src/renderer.ts');const {getProject}=await import('/src/api.ts');
          const base=await getProject(pid,'http://127.0.0.1:8787');const out={};
          const variants={none:null,'red-glow':{id:'red-glow'},'lens-bound (P0b on)':{id:'lens-bound'},'lens-bound (P0b off)':{id:'lens-bound',overrides:{optics:{motionBlur:0,chroma:0,lensWarp:.5,grain:.18,glow:.25,extrude:1}}}};
          for(const [name,look] of Object.entries(variants)){
            const r=new StageRenderer({...base,look},'http://127.0.0.1:8787');await r.load('composite');const c=document.createElement('canvas');
            await r.render(c,0);const t0=performance.now();for(let f=10;f<10+n;f++){await r.render(c,f);c.toDataURL('image/png');}
            out[name]=(performance.now()-t0)/n;r.dispose();}
          return out;}''', [PID, N])
        for k, v in res.items(): print(f'{k:24s} {v:7.1f} ms/frame')
        await b.close()
asyncio.run(main())
