"""One-time migration of the owned song studies to Poppy/Sorrel's finished G cut.

Stops if the user has edited the imported SID shot timing or take; preserves originals.
"""
import copy,json
from import_song_studies import ROOT,OUT,Study,state,record,request,wire_singing,jread
from app.media import encode_preview_proxy,proxy_rel,seek_rel

def existing(slug):
    info=state['projects'][slug];p=request('GET',f"/api/projects/{info['id']}")
    s=Study.__new__(Study);s.slug=slug;s.id=p['id'];s.dir=ROOT/'data/projects'/s.id;s.p=p;s.assets=p['assets'];s.cards=[];s.layers=[];s.recipes={}
    s.by_path={(ROOT/a['source']['importedFrom']).resolve():a for a in s.assets if a.get('source',{}).get('importedFrom')}
    s.identity=next(a for a in s.assets if a.get('name')=='Face · original reference')
    return s,info

s,info=existing('so-i-die');p=s.p;edl='outputs/songs/so-i-die/edit_v5/G/edl.json'
if p['studioImport']['edl']!=edl:
    baseline=jread('outputs/songs/studios/so-i-die-import.json');old={l['id']:l for l in p['layers'] if l['kind']=='media'}
    for l in baseline['layers']:
        if l['kind']=='media':
            assert all(l.get(k)==old.get(l['id'],{}).get(k) for k in ('assetId','start','in','out')),f"User edited {l['id']}; keep it and reconcile manually"
    (OUT/'so-i-die-before-G.json').write_text(json.dumps(p,indent=2))
    s.edl=jread(edl)
    titles=['Head-only glance · arrival','Escalator · maybe','Glance · pleading','Escalator · train','Escalator · tired','Glance · held away','Train · departure']
    ids=[f'so-i-die-shot-{i:02d}' for i in (1,2,3,4,5,7,6)]
    for i,(title,lid) in enumerate(zip(titles,ids)):
        previous=old.get(lid);prior=p['studioImport']['recipes'].get(lid,{})
        source=ROOT/s.edl[i]['src'];run=json.loads((source.parent/'run.json').read_text()) if (source.parent/'run.json').exists() else {}
        reference=run.get('source_image') or prior['reference']
        prompt='Preserve the supplied scene frame: same face, septum and lip rings, short silver-blue hair, flat chest and black leather coat. Subtle head-only glance with a tunnel breeze in the hair. Lips stay closed, no singing or mouthing words. No whole-body turn. Film texture, no skin smoothing.'
        alts=[]
        if i==2:alts=[('outputs/songs/so-i-die/singing/sid_l5l6_esc_front/sid_l5l6_esc_front_mux.mp4','Pleading · escalator front alternative')]
        layer=s.shot(i,title,reference,prompt,alts,9201+i,singing=0<i<6,layer_id=lid)
        if previous:
            for k in ('transform','keys','opacity','mask','blend','hidden','grade'):
                if k in previous:layer[k]=copy.deepcopy(previous[k])
            layer['takes']=list(dict.fromkeys([*previous.get('takes',[]),previous['assetId'],*layer['takes']]))
            if layer['assetId']==previous['assetId']:layer['generation']=previous['generation']
    initial_card_ids={c['id'] for c in baseline['board']['cards'] if c.get('layerId')}
    for c in s.cards:c['id']='g-'+c['id']
    p['board']['cards']=[c for c in p['board']['cards'] if c['id'] not in initial_card_ids]+s.cards
    p['layers']=s.layers+[l for l in p['layers'] if l['kind']!='media']
    p['duration']=sum(e['frames'] for e in s.edl)/24;p['media']['audioClip']['out']=7.89+p['duration']
    p['studioImport'].update(edl=edl,recipes=s.recipes,previousEdl=info['edl'])
    # Spell out the intentional lead-only held-note drive; start=.25 in its file is not the song time.
    for c in p['board']['cards']:
        if c.get('layerId')=='so-i-die-shot-07' and c['kind']=='note':
            c['title']='Held away · lead vocal only'
            c['text']='Song section 22.50–26.93 s. The prepared vocal holds the lead “away”; the backing “so I die” around 25.7 s is omitted from the mouth drive. Keep the held vowel open. Original song audio remains in the composition.'
        if c['id']=='start':c['text']='G cut: separate tired / held-away shots, new pleading take, with escalator-front alternative. Pick a shot card, then Open generation & takes. Compare on the stage before using a take. Lyrics retain your timing.'
    request('PUT',f"/api/projects/{s.id}",json=p)
    info.update(edl=edl,assets=len(p['assets']),cards=len(p['board']['cards']),shots=len(s.edl),duration=p['duration']);record()
    print('So I Die: G cut and split vocal slots imported')

s,info=existing('playboi');p=s.p
if not p['studioImport'].get('carhoodHook'):
    lid='playboi-shot-01';path='outputs/songs/playboi/singing/pb_hook_carhood/pb_hook_carhood_mux.mp4';recipe=jread('outputs/songs/playboi/singing/pb_hook_carhood/run.json')
    a=s.asset(path,'Hook · car hood alternative',lid,recipe)
    l=next(l for l in p['layers'] if l['id']==lid);l['takes']=list(dict.fromkeys([*l.get('takes',[]),a['id']]))
    ref=s.asset(recipe['source_image'],'Car hood · reference')
    s.group('carhood-hook','Hook / car hood direction',1080,0,1030,410,lid)
    s.card(ref,'Car hood · preferred setting',1104,70,'reference',lid,h=300)
    s.card(a,'Car hood hook · compare with booth',1440,70,'asset',lid,h=300)
    s.note('hook-choice','Try the hook here',1776,70,'The car-hood setting was a favorite. This alternate sings the same hook window as the booth. Select this card, open generation & takes, and compare it in the edit.',lid,h=300)
    for c in s.cards:c['id']='hook-'+c['id']
    p['board']['cards'].extend(s.cards)
    for c in p['board']['cards']:
        if c['id']=='group-playboi-shot-02':c['title']='02 / Pool · expression to review'
        if c['id']=='note-playboi-shot-02':c.update(title='To revisit · expression',text='This reference still smiles; the requested direction is restrained and deadpan. Keep this take provisional. Try a new lookbook still before regenerating the vocal.')
    p['studioImport']['carhoodHook']=path
    request('PUT',f"/api/projects/{s.id}",json=p);info.update(assets=len(p['assets']),cards=len(p['board']['cards']));record()
    print('Playboi: car-hood hook alternative and pool review note imported')
wire_singing()
for slug,info in state['projects'].items():
    p=request('GET',f"/api/projects/{info['id']}")
    for c in p['board']['cards']:
        recipe=p['studioImport']['recipes'].get(c.get('layerId'),{})
        if c['kind']=='note' and c['title']=='Next direction' and recipe.get('singing'):
            c.update(title='Singing direction',text=recipe['run']['prompt'])
    if slug=='playboi':
        # A concrete app-generated option beside the accepted car-hood shot; comparison stays explicit.
        a=next((a for a in p['assets'] if a.get('source',{}).get('workflowId')=='ed3fbc575706' and a.get('source',{}).get('seed')==29 and a.get('source',{}).get('layerId')=='playboi-shot-04'),None)
        if a:
            c=next((c for c in p['board']['cards'] if c['id']=='note-playboi-shot-04'),None)
            if c:c.update(kind='asset',assetId=a['id'],title='Made in Create · wind variation',role='asset',text='')
    # Better labels for imported recipes created by the initial import revision.
    for l in p['layers']:
        for d in l.get('generation',{}).get('workflows',{}).values():
            if d.get('mediaFiles',{}).get('audio'):d['mediaFiles']['audio']['name']='Prepared vocal · '+l.get('name','shot')
    request('PUT',f"/api/projects/{p['id']}",json=p)
    (OUT/f'{slug}-working.json').write_text(json.dumps(p,indent=2));info.update(assets=len(p['assets']),cards=len(p['board']['cards']));record()
    made=0
    for a in p['assets']:
        if a['kind']!='video':continue
        root=ROOT/'data/projects'/p['id']
        for rel,full in ((proxy_rel(a['path']),False),(seek_rel(a['path']),True)):
            if not (root/rel).exists():encode_preview_proxy(root/a['path'],root/rel,full=full);made+=1
    print(f'{slug}: {made} studio preview copies prepared',flush=True)
