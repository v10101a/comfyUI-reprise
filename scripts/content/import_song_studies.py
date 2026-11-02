"""Bring reviewed song EDLs into separate Typeset projects, with linked boards/takes.

Creates each study once, records its ID, and refuses to overwrite it on subsequent runs.
Media is hard-linked into the new project (copied across filesystems); manifests retain recipes.
No generation, original-project mutation, or public publishing occurs here.
"""
from __future__ import annotations
import copy, hashlib, json, math, os, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
import httpx
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server'))
from app.media import probe_media, extract_frame

OUT=ROOT/'outputs/songs/studios';OUT.mkdir(parents=True,exist_ok=True)
MANIFEST=OUT/'manifest.json'
state=json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {'workflows':{},'projects':{}}
api=httpx.Client(base_url='http://127.0.0.1:8787',timeout=120)
FPS=24
def record(): MANIFEST.write_text(json.dumps(state,indent=2))
def request(method,path,**kw):
    r=api.request(method,path,**kw);r.raise_for_status();return r.json()
def jread(path):return json.loads((ROOT/path).read_text())
def link(src:Path,dest:Path):
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():return
    try:os.link(src,dest)
    except OSError:shutil.copy2(src,dest)

def workflow(key,name,src,ports,output):
    if key in state['workflows']:return state['workflows'][key]
    graph=jread(src)
    for node,title in ports.values():graph[node].setdefault('_meta',{})['title']=title
    for node in graph.values():
        if 'filename_prefix' in node.get('inputs',{}):node['inputs']['filename_prefix']='typeset/studies/'+key
    w=request('POST','/api/workflows',json={'name':name,'graph':graph})
    inputs={}
    for key2,(node,title) in ports.items():
        cls=graph[node]['class_type'];field='image' if cls=='LoadImage' else 'noise_seed' if cls=='RandomNoise' else 'prompt'
        inputs[key2]={'node':node,'field':field}
    if key!='lookbook':inputs['length']={'node':'6','field':'length'}
    w=request('PUT',f"/api/workflows/{w['id']}",json={'inputs':inputs,'output':output})
    state['workflows'][key]=w['id'];record();return w['id']

H3=workflow('silent','Silent motion · H3','outputs/songs/playboi/lookbook_v4/broll/br_pool/workflow.json',
            {'image':('5','Scene reference'),'prompt':('6','Direction'),'seed':('7','Variation seed')},{'node':'15','type':'video'})
IDENTITY=workflow('identity_scene','Identity + scene motion · H3','outputs/songs/so-i-die/clips/sid_glance_walk_a/workflow.json',
            {'identity':('5','Face reference'),'image':('16','Scene reference'),'prompt':('6','Direction'),'seed':('7','Variation seed')},{'node':'15','type':'video'})
LOOKBOOK=workflow('lookbook','Lookbook still · face + hair','outputs/songs/playboi/lookbook_v4/raw/booth_deadpan/workflow.json',
            {'identity':('5','Face reference'),'hair':('50','Hair reference'),'prompt':('6','Direction'),'seed':('7','Variation seed')},{'node':'411','type':'image'})

class Study:
    def __init__(self,slug,original_id,name,edl_path,song_in):
        self.slug=slug;self.original_id=original_id;self.edl_path=edl_path;self.song_in=song_in
        self.original=request('GET',f'/api/projects/{original_id}')
        (OUT/f'{slug}-original.json').write_text(json.dumps(self.original,indent=2))
        prior=state['projects'].get(slug)
        if prior and prior.get('complete'):raise RuntimeError(f"{slug} study already created; refusing to overwrite user edits ({prior['id']})")
        self.id=prior['id'] if prior else request('POST','/api/projects',json={'name':name})['id']
        state['projects'][slug]={'id':self.id,'name':name,'originalId':original_id,'edl':edl_path,'complete':False};record()
        self.dir=ROOT/'data/projects'/self.id;self.assets=[];self.cards=[];self.layers=[];self.by_path={};self.recipes={}
        self.p=copy.deepcopy(self.original);self.p.update(id=self.id,name=name,assets=self.assets,layers=self.layers,shots=[],surfaces=[],frame=None)
        self.p['media']['video']=None;self.p['analysis']={};self.p['fps']=FPS
        self.p['studioImport']={'originalProject':original_id,'edl':edl_path,'at':datetime.now(timezone.utc).isoformat()}
        self.edl=jread(edl_path);self.p['duration']=sum(x['frames'] for x in self.edl)/FPS
        audio=self.original['media']['audio'];src=ROOT/'data/projects'/original_id/audio['path']
        rel='media/song'+src.suffix;link(src,self.dir/rel);self.p['media']['audio']={**audio,'path':rel}
        old_clip=self.original['media'].get('audioClip') or {'in':0,'offset':0}
        shift=old_clip['in']-old_clip.get('offset',0)-song_in
        self.p['media']['audioClip']={'in':song_in,'out':min(audio['duration'],song_in+self.p['duration']),'offset':0}
        for word in self.p['words']:word['start']=round(word['start']+shift,6);word['end']=round(word['end']+shift,6)
        self.p['analysis']['words']='analysis/words.json';(self.dir/'analysis').mkdir(exist_ok=True)
        (self.dir/'analysis/words.json').write_text(json.dumps({'words':self.p['words']},indent=2))
        beats=self.original['analysis'].get('beats')
        if beats:link(ROOT/'data/projects'/original_id/beats,self.dir/beats);self.p['analysis']['beats']=beats
        self.identity=self.asset('outputs/ffm_angel/v3/ref_face.png','Face · original reference')
        self.group('direction','Identity & direction',0,0,1030,410)
        self.card(self.identity,'Face · original reference',24,70,role='character',w=220,h=300)
        self.note('start','Start here',510,70,'Pick a shot card to select its layer, then open generation & takes. Compare a take on the stage and use it when ready. The timeline contains individual shots; the song and existing lyric edits are preserved.',w=240,h=300)
        self.note('singing','Singing recipe',770,70,'Singing takes use Wan 2.2 S2V with isolated vocals, 0.8× vocal speed, 0.25 s pre-roll, then motion interpolation to 24 fps. Those finished takes and run settings are imported. H3 is configured for silent visual alternatives; it is not the singing pipeline.',w=235,h=300)

    def asset(self,path,name,layer=None,recipe=None):
        path=Path(path);src=path if path.is_absolute() else ROOT/path;src=src.resolve()
        if src in self.by_path:return self.by_path[src]
        if not src.is_file():raise FileNotFoundError(src)
        identity=hashlib.sha256(str(src.relative_to(ROOT)).encode()).hexdigest()[:12];aid='a_'+identity
        rel=f'media/{identity}{src.suffix.lower()}';link(src,self.dir/rel)
        kind='image' if src.suffix.lower() in ('.png','.jpg','.jpeg','.webp') else 'video'
        if kind=='image':
            with Image.open(src) as im:w,h=im.size
            a=dict(id=aid,kind=kind,path=rel,width=w,height=h,name=name)
        else:a={'id':aid,'kind':kind,'name':name,**probe_media(self.dir/rel,rel).model_dump(mode='json')}
        a['source']={'kind':'workflow' if layer else 'upload','importedFrom':str(src.relative_to(ROOT))}
        if layer:a['source'].update(layerId=layer,workflowName=(recipe or {}).get('engine','Imported Comfy take'))
        if recipe:a['source'].update(recipe=recipe,seed=recipe.get('seed'),promptId=recipe.get('prompt_id'))
        self.assets.append(a);self.by_path[src]=a;return a

    def group(self,id,title,x,y,w=1030,h=390,layer=None):self.cards.append(dict(id=id,kind='group',title=title,x=x,y=y,w=w,h=h,role='reference',**({'layerId':layer} if layer else {})))
    def card(self,asset,title,x,y,role='asset',layer=None,w=310,h=245):
        self.cards.append(dict(id=f'card_{len(self.cards)}',kind='asset',title=title,assetId=asset['id'],x=x,y=y,w=w,h=h,role=role,**({'layerId':layer} if layer else {})))
    def note(self,id,title,x,y,text,layer=None,w=310,h=245):
        self.cards.append(dict(id=id,kind='note',title=title,text=text,x=x,y=y,w=w,h=h,role='motion',**({'layerId':layer} if layer else {})))

    def shot(self,i,title,reference,prompt,alts=(),seed=7001,singing=False,layer_id=None):
        e=self.edl[i];lid=layer_id or f'{self.slug}-shot-{i+1:02d}';src=ROOT/e['src'];run=src.parent/'run.json'
        recipe=json.loads(run.read_text()) if run.exists() else {}
        if not recipe and (src.parent/'workflow.json').exists():recipe={'workflow':str((src.parent/'workflow.json').relative_to(ROOT))}
        a=self.asset(e['src'],title+' · current',lid,recipe);ref=self.asset(reference,title+' · reference')
        cin=e.get('inFrame',0)/FPS if 'inFrame' in e else max(0,e.get('in',0));duration=e['frames']/FPS
        takes=[a['id']];alt_assets=[]
        for path,label in alts:
            ap=ROOT/path;ar=ap.parent/'run.json';r=json.loads(ar.read_text()) if ar.exists() else {}
            alt=self.asset(path,label,lid,r);takes.append(alt['id']);alt_assets.append(alt)
        wid=H3 if self.slug=='playboi' else IDENTITY
        inputs={'prompt':prompt,'seed':seed,'length':max(49,int(math.ceil((cin+duration)*FPS/4))*4+1)}
        sources={'image':ref['id']}
        if wid==IDENTITY:sources['identity']=self.identity['id']
        layer=dict(id=lid,kind='media',name=title,assetId=a['id'],start=e['startFrame']/FPS,**{'in':cin},out=cin+duration,takes=takes,
                   generation={'workflowId':wid,'workflows':{wid:{'inputs':inputs,'sources':sources,'variants':1}}})
        self.layers.append(layer)
        row=i//2;col=i%2;x=col*1080;y=470+row*440
        self.group('group-'+lid,f'{i+1:02d} / {title}',x,y,1030,405,lid)
        self.card(ref,'Reference · '+title,x+24,y+72,'reference',lid)
        self.card(a,('Singing' if singing else 'Silent')+' · current take',x+360,y+72,'asset',lid)
        if alt_assets:self.card(alt_assets[0],alt_assets[0]['name'],x+696,y+72,'asset',lid)
        else:self.note('note-'+lid,'Next direction',x+696,y+72,prompt,lid)
        self.recipes[lid]={'edl':e,'run':recipe,'reference':reference,'alternatives':[p for p,_ in alts],'singing':singing}
        # Keep the complete generation settings in a readable note without covering the main shot grid.
        if singing:self.note('recipe-'+lid,title+' · vocal timing',2240,470+i*290,
            f"Vocal section start: {recipe.get('start')} s. Seed {recipe.get('seed')}. 1152×656, 4 steps.\n\n{recipe.get('prompt','')}\n\nCurrent take is already retimed; do not stretch it again.",lid,w=340,h=260)
        return layer

    def finish(self):
        # Media sit under both text passes. Old cut mattes are deliberately not copied onto new shots.
        self.layers.extend([{'id':'text-behind','kind':'text','which':'behind'},{'id':'subject','kind':'subject'},{'id':'text-front','kind':'text','which':'front'}])
        self.p['board']={'cards':self.cards,'view':{'x':22,'y':20,'zoom':.53}}
        self.p['studioImport']['recipes']=self.recipes
        saved=request('PUT',f'/api/projects/{self.id}',json=self.p)
        state['projects'][self.slug].update(complete=True,url=f'http://127.0.0.1:5174/#/studio?project={self.id}',assets=len(self.assets),cards=len(self.cards),shots=len(self.edl),duration=self.p['duration'])
        (OUT/f'{self.slug}-import.json').write_text(json.dumps(saved,indent=2));record()
        print(json.dumps(state['projects'][self.slug]),flush=True)

if not state['projects'].get('playboi',{}).get('complete'):
    s=Study('playboi','94c8b4f6-a6b1-4152-ad0e-52ca6647bda1','Playboi · shot studio','outputs/songs/playboi/edit_v7/edl.json',12.12)
    hair=s.asset('outputs/ffm_angel/v3/ref_hair2.png','Hair · platinum shag');s.card(hair,'Hair · platinum shag',270,70,'wardrobe',w=220,h=300)
    cfg=jread('outputs/songs/playboi/lookbook_v4/jobs.json');scenes={x['name']:x for x in cfg['shots']}
    def ref(name):return f'outputs/songs/playboi/lookbook_v4/raw/{name}/{name}_f024_00001_.png'
    ids=['booth_deadpan','pool_night','booth_deadpan','car_hood','motel_hallway','mirror_neon','pool_night','car_hood']
    titles=['Booth hook','Pool · uh-huh','Booth · play boy','Car hood · see this','Hallway · drop','Mirror · drop','Pool · drop','Car hood · drop']
    broll={x['name']:x for x in jread('outputs/songs/playboi/lookbook_v4/broll_jobs.json')}
    for i,(name,title) in enumerate(zip(ids,titles)):
        prompt=(broll[['br_hallway','br_mirror','br_pool','br_carhood'][i-4]]['prompt'] if i>=4 else
                f"Match the supplied first frame: same face, piercings, platinum shag, striped shirt, tie and headphones. {scenes[name]['prompt']} Lips remain closed, no singing, no talking, no mouthing words. A soft breeze moves a few hair strands. This is a silent alternative with the original song playing over it.")
        alts=[('outputs/songs/playboi/singing/pb_hook_booth_lean/pb_hook_booth_lean_push.mp4','Booth hook · lean alternative')] if i==0 else []
        layer=s.shot(i,title,ref(name),prompt,alts,5101+i,singing=i<4)
        layer['generation']['workflows'][LOOKBOOK]={'inputs':{'prompt':cfg['identity']+' '+scenes[name]['prompt'],'seed':scenes[name]['seed']},'sources':{'identity':s.identity['id'],'hair':hair['id']},'variants':1}
    s.finish()

if not state['projects'].get('so-i-die',{}).get('complete'):
    s=Study('so-i-die','adb18080-de65-46c5-9452-4ef24c54cff5','So I Die · shot studio','outputs/songs/so-i-die/edit_v5/E_s2v/edl.json',7.89)
    walk=jread('outputs/songs/so-i-die/clips/sid_glance_walk_a/request.json')
    outfit=s.asset(walk['first'],'Coat & hair · subway reference');s.card(outfit,'Coat & short silver-blue hair',270,70,'wardrobe',w=220,h=300)
    titles=['Head-only glance · arrival','Escalator · maybe','Glance · pleading','Escalator · train','Escalator · hide away','Train · departure']
    for i,title in enumerate(titles):
        e=s.edl[i];run=ROOT/e['src'];recipe=json.loads((run.parent/'run.json').read_text()) if (run.parent/'run.json').exists() else {}
        reference=walk['first'] if i==0 else recipe.get('source_image')
        if not reference:
            frame=OUT/f'sid-shot-{i+1}-reference.png';extract_frame(run,0,frame);reference=str(frame.relative_to(ROOT))
        prompt=(walk['prompt'] if i==0 else 'Use <Picture 1> only for facial identity and preserve the supplied scene frame exactly: same face, septum and lip rings, short silver-blue layered hair, flat chest and black leather coat. '+
                ('A train passes behind the still figure, lit windows streaking past. ' if i==5 else 'Subtle head movement, body stays in its original pose. ')+
                'A tunnel breeze lifts hair strands and the coat collar. Calm closed lips and still jaw, no singing, no talking, no mouthing words. Natural fluorescent light, film texture, no beauty smoothing. No whole-body turn.')
        alts=[]
        if i==0:alts=[('outputs/songs/so-i-die/clips/sid_glance_walk_b/sid_glance_walk_b_00001-audio.mp4','Arrival · quieter glance B')]
        if i==1:alts=[('outputs/songs/so-i-die/singing/sid_esc_move_a/sid_esc_move_a_mux.mp4','Escalator · singing alternative A')]
        if i==4:alts=[('outputs/songs/so-i-die/singing/sid_glance2_l9l10/sid_glance2_l9l10_mux.mp4','Hide away · glance alternative')]
        s.shot(i,title,reference,prompt,alts,9201+i,singing=0<i<5)
    # Preserve the smoking exploration as an optional asset/card, never insert it into the current cut.
    smoke_path=next((ROOT/'outputs/songs/so-i-die/clips/sid_smoke_wall_wind').glob('*_00001-audio.mp4'))
    smoke=s.asset(smoke_path,'Smoking · optional silent exploration');s.card(smoke,'Optional · smoking exploration',1080,70,'motion',w=360,h=300)
    s.finish()


def wire_singing():
    """Add the exact prepared vocal and return timing to each imported singing slot, once."""
    wid='ed3fbc575706'
    for slug,info in state['projects'].items():
        p=request('GET',f"/api/projects/{info['id']}");root=ROOT/'data/projects'/p['id'];changed=False
        for layer in p['layers']:
            recipe=p['studioImport']['recipes'].get(layer['id'],{})
            if not recipe.get('singing'):continue
            gen=layer.setdefault('generation',{});drafts=gen.setdefault('workflows',{})
            if wid in drafts:continue  # preserve any user changes to an already imported recipe
            meta=recipe['run'];src=ROOT/recipe['edl']['src'];folder=src.parent
            if meta.get('length',0)>101:continue  # pending split takes replace the old long held-note slot
            for path in ('gen.wav','mux.wav','ref.png'):
                if not (folder/path).is_file():raise FileNotFoundError(folder/path)
            rel=f'audio/{folder.name}/drive.wav';mux=f'audio/{folder.name}/song.wav';link(folder/'gen.wav',root/rel);link(folder/'mux.wav',root/mux)
            rid='a_'+hashlib.sha256(str((folder/'ref.png').relative_to(ROOT)).encode()).hexdigest()[:12]
            rpath=f'media/{rid}_prepared.png';link(folder/'ref.png',root/rpath)
            if not any(a['id']==rid for a in p['assets']):
                with Image.open(folder/'ref.png') as im:w,h=im.size
                p['assets'].append(dict(id=rid,kind='image',path=rpath,name=layer['name']+' · generation frame',width=w,height=h,
                    source={'kind':'upload','importedFrom':str((folder/'ref.png').relative_to(ROOT))}))
            duration=probe_media(root/rel,rel).duration
            drafts[wid]={'inputs':{'prompt':meta['prompt'],'seed':meta['seed'],'length':meta['length'],'width':meta['size'][0],'height':meta['size'][1]},
                'sources':{'image':rid,'audio':'@prepared'},'variants':1,
                'mediaFiles':{'audio':{'path':rel,'name':f"Prepared vocal · {layer['name']}",'duration':duration}},
                'postprocess':{'timeScale':meta.get('stretch',1),'trimStart':meta.get('pre',0),'fps':24,'audio':mux}}
            gen['workflowId']=wid;changed=True
        if changed:
            for c in p['board']['cards']:
                if c['id']=='singing':c['text']='Singing shots open their S2V recipe in Create. The prepared vocal is matched to that take, including slowed delivery and pre-roll; the app returns the result to song timing at 24 fps. Edit the prompt/reference or seed, generate, then compare before using the take. Moving a shot does not rewrite its vocal.'
            p=request('PUT',f"/api/projects/{p['id']}",json=p)
            info['assets']=len(p['assets']);record();print(f"{slug}: prepared singing recipes connected",flush=True)

wire_singing()
