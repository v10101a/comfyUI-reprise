"""Unit checks for the looks.ts API U consumes (runs the TS modules in the browser via Vite).
Usage: server/.venv/bin/python apps/web/scripts/check_looks_api.py"""
import asyncio, os
from playwright.async_api import async_playwright
BASE = os.environ.get('TYPESET_WEB_URL', 'http://127.0.0.1:5174')
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(); await pg.goto(BASE + '/#/render?project=sample&layer=text')
        await pg.wait_for_function('window.__typeset !== undefined'); await pg.evaluate('window.__typeset.ready')
        r = await pg.evaluate('''async()=>{
          const L=await import('/src/looks.ts');const {StageRenderer}=await import('/src/renderer.ts');
          const base=await fetch('/sample/project.json').then(r=>r.json());const fails=[];const ok=(c,m)=>{if(!c)fails.push(m)};
          ok(L.LOOKS.length===7&&L.LOOKS.every(l=>l.id&&l.name&&l.swatch.length&&l.fonts.length&&l.description),'LOOKS shape');
          ok(!L.LOOKS.some(l=>/brat/i.test(l.id+l.name+l.description)),'no artist-branded names');
          ok(L.lookOf(base)===undefined,'no look by default');
          const p1=L.setLook(base,'red-glow');ok(base.look===undefined&&p1.look.id==='red-glow','setLook pure');
          ok(L.lookOf(p1).palette.text==='#ff1a1a','preset resolved');
          const p2=L.setLookOverrides(p1,{palette:{text:'#00ff00'}});ok(L.lookOf(p2).palette.text==='#00ff00'&&L.lookOf(p2).palette.accent,'overrides merge');
          ok(L.setLook(p2,'default').look===null,'default clears');
          // repeated lyric → hook
          const w=(id,text,line,s)=>({id,text,start:s,end:s+.5,lineId:line,placement:'overlay',preset:'pop'});
          const song={...base,words:[w('a','hold','l0',0),w('b','on','l0',.3),w('c','every','l1',1),w('d','word','l1',1.3),w('e','hold','l2',2),w('f','on','l2',2.3)],lineMeta:null};
          ok(L.lineIsHook(song,'l0')&&L.lineIsHook(song,'l2')&&!L.lineIsHook(song,'l1'),'repeat heuristic');
          ok(!L.lineIsHook(L.setLineMeta(song,'l0',{hook:false}),'l0'),'lineMeta.hook=false wins');
          const quiet=L.setLookOverrides(L.setLook(song,'lens-bound'),{quiet:'hooks-only'});
          ok(!L.wordIsShown(quiet,song.words[2])&&L.wordIsShown(quiet,song.words[0]),'hooks-only hides verses');
          ok(!L.wordIsShown(L.setWordHidden(song,'a',true),{...song.words[0],hidden:true}),'Word.hidden');
          ok(!L.wordIsShown(L.setLineMeta(song,'l1',{hidden:true}),song.words[2]),'lineMeta.hidden');
          ok(L.heroWordId(song,'l1')==='d','hero fallback: "every" is a stopword, so "word"');
          const h=L.setWordHero(song,'c',true);ok(L.heroWordId(h,'l1')==='c','Word.hero override');
          ok(L.setLineMeta(song,'l1',{heroWordId:'c'}).lineMeta.l1.heroWordId==='c','lineMeta heroWordId');
          // renderer honours hidden + quiet
          const c=document.createElement('canvas').getContext('2d');
          const r1=new StageRenderer(quiet);ok(r1.units(c).every(u=>u.lineId!=='l1'),'renderer drops quiet lines');
          return fails;}''')
        print('FAIL', r) if r else print('PASS looks API: LOOKS, lookOf, setLook/overrides, lineMeta, hero, hidden, hooks-only, repeat heuristic')
        await b.close()
asyncio.run(main())
