"""Read-only browser checks for preview frame reuse and reduced-resolution look cards.

Uses local fixture projects through Vite; blocks writes to user projects. Cached and
uncached frames must be identical, including after edits, quality changes and seeks.
"""
import argparse
import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECTS = ['54da2790-92c6-4737-bc43-81a207e47ab5', '14ef9e95-1d22-4bc1-8e42-5a1db01368ee']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--origin', default='http://127.0.0.1:5174')
    ap.add_argument('--projects', nargs='+', default=PROJECTS)
    ap.add_argument('--out', type=Path, default=Path('outputs/perf/preview-cache'))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'projects': []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.route('**/api/**', lambda route: route.continue_()
                   if route.request.method in ('GET', 'HEAD', 'OPTIONS') else route.abort())
        page.goto(args.origin + '/#/render?project=' + args.projects[0], wait_until='domcontentloaded')
        page.wait_for_function('window.__typeset !== undefined')
        page.evaluate('() => window.__typeset.ready')
        for pid in args.projects:
            result = page.evaluate('''async pid => {
                const {StageRenderer}=await import('/src/renderer.ts');
                const {setLook,LOOKS}=await import('/src/looks.ts');
                const {lookPreviewProject}=await import('/src/studio/LookPicker.tsx');
                const p=await fetch('/api/projects/'+pid).then(r=>r.json());
                const original=JSON.stringify(p);
                const r=new StageRenderer(p);r.draftMedia=true;await r.load();
                const c=document.createElement('canvas'),checks=[],pictures={};
                let paints=0;const paint=r.paintVideo.bind(r);
                r.paintVideo=(...a)=>{paints++;return paint(...a);};
                const pixels=()=>new Uint8ClampedArray(c.getContext('2d').getImageData(0,0,c.width,c.height).data);
                const check=async(label,q,frame,opts={proxy:true},layer='composite')=>{
                    r.project=q;const n=paints;
                    await r.render(c,frame,layer,{...opts,cacheMedia:true,cacheLayouts:true});const cached=pixels(),missPaints=paints-n;
                    const m=paints;await r.render(c,frame,layer,{...opts,cacheMedia:true,cacheLayouts:true});const warm=pixels(),hitPaints=paints-m;
                    // Force fresh placement as well as fresh footage, so a stale plan cannot make both sides agree.
                    r.plan=undefined;
                    const o=paints;await r.render(c,frame,layer,{...opts,cacheMedia:false,cacheLayouts:false});const plain=pixels(),plainPaints=paints-o;
                    let diff=0,max=0;for(let i=0;i<plain.length;i++){
                        const d=Math.max(Math.abs(plain[i]-cached[i]),Math.abs(plain[i]-warm[i]));if(d){diff++;max=Math.max(max,d);}}
                    checks.push({label,frame,layer,missPaints,hitPaints,plainPaints,diff,max,width:c.width,height:c.height});
                    if(diff||hitPaints!==0)throw new Error(JSON.stringify(checks.at(-1)));
                };
                const f=144,base={...setLook(p,'flat-card'),grade:{id:'film',amount:.6}};
                await check('cold + warm',base,f);
                const moved={...base,words:base.words.map(w=>({...w,position:{x:.65,y:.4},autoPlace:false}))};
                await check('moved text',moved,f);
                if(checks.at(-1).missPaints!==0)throw new Error('Moving text repainted the footage');
                await check('changed text',{...moved,words:moved.words.map(w=>({...w,text:w.text+'!'}))},f);
                if(checks.at(-1).missPaints!==0)throw new Error('Editing text repainted the footage');
                await check('changed timing',{...base,words:base.words.map(w=>({...w,start:w.start+.2,end:w.end+.2}))},f);
                await check('changed grade',{...base,grade:{id:'mono',amount:1}},f);
                await check('next frame',base,f+1);
                await check('backwards seek',base,24);
                await check('full-size seek copies',base,f,{full:true});
                await check('original media',base,f,{});
                await check('back to proxies',base,f);
                r.crop={fps:p.fps,aspect:'9:16',frames:[{f:0,x:.1,y:0,w:.75,h:1}]};
                await check('crop changed',base,f);
                r.crop=undefined;
                for(const id of ['neon','graffiti','ticker','glyph','xerox']){
                    const q=setLook(base,id,id==='glyph'?{fill:{region:'subject',hooks:false}}:undefined);
                    await check(id,q,f);
                    if(id==='glyph')await check('glyph alpha',q,f,{proxy:true},'text');
                }
                const before=c.toDataURL();await r.render(c,f+1,'composite',{proxy:true,cacheMedia:true,stale:()=>true});
                if(c.toDataURL()!==before)throw new Error('A stale frame painted the canvas');
                // No option means the original/export path, even on a renderer that has previously cached media.
                r.project=base;const n=paints;await r.render(c,f);if(paints===n)throw new Error('Cache leaked into default rendering');
                for(const info of LOOKS){
                    const q=setLook(p,info.id==='default'?null:info.id);
                    r.project=lookPreviewProject(q);await r.render(c,f,'composite',{proxy:true,heavyOptics:false,cacheMedia:true,cacheLayouts:true,previewScale:r.project.height/q.height});
                    if(Math.max(c.width,c.height)>480)throw new Error('Thumbnail rendered at full project size');
                    const small=pixels();if(!small.some((v,i)=>i%4===3&&v))throw new Error('Empty thumbnail: '+info.id);
                    pictures[info.id+'-small']=c.toDataURL('image/png');
                    if(['flat-card','paper-cut','neon','hud','ticker','glyph','xerox'].includes(info.id)){
                        r.project=q;await r.render(c,f,'composite',{proxy:true,heavyOptics:false});
                        const out=document.createElement('canvas'),s=lookPreviewProject(q);out.width=s.width;out.height=s.height;
                        out.getContext('2d').drawImage(c,0,0,out.width,out.height);pictures[info.id+'-reference']=out.toDataURL('image/png');
                    }
                }
                // Revisit every look on another frame, after intervening looks: the placement plan must be reusable
                // and produce the same pixels as a fresh solve. This is the actual thumbnail-scrubbing workload.
                for(const info of LOOKS){
                    const q=lookPreviewProject(setLook(p,info.id==='default'?null:info.id));
                    await check('thumbnail revisit '+info.id,q,f+1,{proxy:true,heavyOptics:false,previewScale:q.height/p.height});
                }
                if(JSON.stringify(p)!==original)throw new Error('Preview changed the source project');
                r.dispose();return {pid,checks,pictures,thumbnailCount:LOOKS.length};
            }''', pid)
            dest = args.out / pid[:8]
            dest.mkdir(exist_ok=True)
            for name, data in result.pop('pictures').items():
                (dest / (name + '.png')).write_bytes(base64.b64decode(data.split(',')[1]))
            report['projects'].append(result)
            (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps({'project': pid, 'checks': len(result['checks']), 'thumbs': result['thumbnailCount'], 'passed': True}), flush=True)
        browser.close()


if __name__ == '__main__':
    main()
