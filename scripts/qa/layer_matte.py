"""Layer-targeted matte UI + real renderer pixels, using isolated API/media fixtures."""
import base64, copy, io, json, os, re, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, expect

OUT=Path('outputs/progress/layer-matte');OUT.mkdir(parents=True,exist_ok=True)
BASE=os.environ.get('TYPESET_UI_URL','http://127.0.0.1:5174');PID='layer-matte-qa'
png=io.BytesIO();Image.new('RGB',(64,64),'blue').save(png,format='PNG')
img='data:image/png;base64,'+base64.b64encode(png.getvalue()).decode()
source=dict(layerId='shot',assetId='face',path=img,kind='video',**{'in':.5},out=1.5,width=64,height=64,fps=24)
project=dict(version=1,id=PID,name='Layer matte study',width=128,height=96,fps=24,duration=3,media={},analysis={},shots=[],surfaces=[],grade=None,
    style=dict(fontFamily='Inter',fontWeight=700,fontSize=.1,fill='#ffffff',align='center'),words=[],
    assets=[dict(id='face',kind='image',path=img,name='Character',width=64,height=64),dict(id='other',kind='image',path=img,name='Wardrobe',width=64,height=64)],
    layers=[dict(id='shot',kind='media',name='Character layer',assetId='face',start=1,**{'in':.5},out=1.5,transform=dict(x=.25,scale=.5),mask='subject'),dict(id='subject',kind='subject'),
            dict(id='wardrobe',kind='media',name='Wardrobe layer',assetId='other',start=0,**{'in':0},out=3,hidden=True)])
saved=copy.deepcopy(project);runs=[];errors=[]
with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
    tmp=Path(tmp)
    for f in range(24):
        im=Image.new('RGBA',(64,64));ImageDraw.Draw(im).rectangle((16,16,47,47),fill=(255,0,0,255) if f<12 else (0,255,0,255));im.save(tmp/f'fg_{f:05d}.png')
    subprocess.run(['/opt/homebrew/bin/ffmpeg','-v','error','-y','-framerate','24','-i',str(tmp/'fg_%05d.png'),'-c:v','libvpx-vp9','-pix_fmt','yuva420p','-auto-alt-ref','0',str(tmp/'fg.webm')],check=True)
    browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport=dict(width=1440,height=1000));page.on('pageerror',lambda e:errors.append(str(e)))
    def api(r):
        global saved
        req=r.request;path=req.url.split('/api/',1)[-1].split('?',1)[0]
        if path==f'projects/{PID}':
            if req.method=='PUT':saved=req.post_data_json
            r.fulfill(json=saved)
        elif path=='projects':r.fulfill(json=[saved])
        elif path=='health':r.fulfill(json=dict(comfyui=True))
        elif path=='workflows':r.fulfill(json=[])
        elif path=='session':r.fulfill(json=dict(projectId=PID))
        elif path=='jobs':r.fulfill(json=[])
        elif path==f'projects/{PID}/analyze/matte':
            body=req.post_data_json;runs.append(body);r.fulfill(json=dict(id='job',kind='matte',layerId=body['layerId'],status='done',projectId=PID,result={'layerId':body['layerId']}))
        else:r.fulfill(status=404,json=dict(detail='Disabled in layer matte QA'))
    page.route('**/api/**',api)
    def media(r):
        data=(tmp/'fg.webm').read_bytes();n=len(data);m=re.match(r'bytes=(\d+)-(\d*)',r.request.headers.get('range',''))
        headers={'Accept-Ranges':'bytes'}
        if m:
            start=int(m[1]);end=min(n-1,int(m[2]) if m[2] else n-1);headers['Content-Range']=f'bytes {start}-{end}/{n}'
            r.fulfill(status=206,body=data[start:end+1],content_type='video/webm',headers=headers)
        else:r.fulfill(body=data,content_type='video/webm',headers=headers)
    page.route(f'**/files/projects/{PID}/analysis/matte/fg.webm',media)
    page.goto(f'{BASE}/#/studio?project={PID}');page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    page.get_by_role('button',name='Pipeline',exact=True).click()
    selector=page.get_by_label('Matte source layer');expect(selector).to_have_value('shot')
    selector.select_option('wardrobe');page.get_by_role('button',name='Run Subject matte',exact=True).click()
    expect(selector).to_be_enabled(timeout=10000);assert runs==[{'layerId':'wardrobe'}],runs
    selector.select_option('');expect(page.get_by_role('button',name='Run Subject matte',exact=True)).to_be_disabled()
    selector.select_option('shot');page.screenshot(path=str(OUT/'pipeline.png'))
    # Render with the same StageRenderer used for previews and exports; no model calls.
    p=copy.deepcopy(project);p['analysis']=dict(matte='analysis/matte/',matteSource=source)
    result=page.evaluate('''async p=>{
      const {StageRenderer}=await import('/src/renderer.ts');const r=new StageRenderer(p);await r.load();
      const c=document.createElement('canvas');const pixel=(x,y)=>[...c.getContext('2d').getImageData(x,y,1,1).data];
      const draw=async f=>{await r.render(c,f);return {center:pixel(96,48),outside:pixel(60,48),time:r.matte.currentTime,duration:r.matte.duration};};
      const before=await draw(12),early=await draw(30),late=await draw(42),after=await draw(60);
      p.layers[0].transform={x:0,scale:.5,rotate:90};await r.render(c,30);const moved={new:pixel(64,48),old:pixel(96,48)};
      p.layers[0].opacity=.5;await r.render(c,30);const translucent=pixel(64,48);
      p.layers[0].assetId='other';const replaced=await draw(30);
      r.dispose();return {before,early,late,after,moved,translucent,replaced};
    }''',p)
    assert result['before']['center'][3]==0 and result['after']['center'][3]==0,result
    assert result['early']['center'][0]>220 and result['early']['center'][1]<30,result
    assert result['late']['center'][1]>220 and result['late']['center'][0]<30,result
    assert result['early']['outside'][3]==0,result
    assert result['moved']['new'][0]>220 and result['moved']['old'][3]==0,result
    assert result['replaced']['center'][3]==0,result
    assert not errors,errors
    report=dict(requests=runs,pixels=result,browserErrors=errors);(OUT/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));browser.close()
