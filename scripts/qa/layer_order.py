"""Reorder timeline visuals through real pointer gestures; assert pixels, persistence and compact rows."""
import base64,copy,json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
PID='layer-order-qa';OUT=Path('outputs/progress/layer-order');OUT.mkdir(parents=True,exist_ok=True)
def asset(id,color):
 svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="96"><rect width="160" height="96" fill="{color}"/></svg>'
 return dict(id=id,kind='image',name=id,path='data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode(),width=160,height=96)
saved=dict(version=1,id=PID,name='Display order',width=160,height=96,fps=24,duration=12,media={},analysis={},shots=[],surfaces=[],grade=None,words=[],
 style=dict(fontFamily='Inter',fontWeight=700,fontSize=.1,fill='#ffffff',align='center'),
 assets=[asset('older','#ff0000'),asset('newer','#0000ff'),asset('later','#00ff00')],
 layers=[dict(id='older',kind='media',assetId='older',name='Older take',start=.11,**{'in':.2},out=4.2,keys=[dict(t=0,opacity=1)],transform=dict(scale=1.1)),
         dict(id='newer',kind='media',assetId='newer',name='Newer take',start=0,**{'in':0},out=4),
         dict(id='later',kind='media',assetId='later',name='Later shot',start=5,**{'in':0},out=2),
         dict(id='text',kind='text',which='front')])
original=copy.deepcopy(saved);errors=[];checks=[]
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);page=b.new_page(viewport=dict(width=1440,height=1000));page.on('pageerror',lambda e:errors.append(str(e)))
 def api(r):
  global saved
  req=r.request;path=req.url.split('/api/',1)[-1].split('?',1)[0]
  if path==f'projects/{PID}':
   if req.method=='PUT':saved=req.post_data_json
   r.fulfill(json=saved)
  elif path=='projects':r.fulfill(json=[saved])
  elif path in ['jobs','workflows','looks/saved']:r.fulfill(json=[])
  elif path=='session':r.fulfill(json={'projectId':PID})
  elif path=='health':r.fulfill(json={'comfyui':True})
  else:r.fulfill(status=404,json={'detail':'Isolated QA'})
 page.route('**/api/**',api)
 def save():
  with page.expect_response(lambda r:r.request.method=='PUT' and f'projects/{PID}' in r.url):page.locator('.s-save').click()
 def clip(id):return page.locator(f'.ly-clip[data-layer-id="{id}"]')
 def point(id):
  r=clip(id).bounding_box();return r['x']+min(70,r['width']/2),r['y']+r['height']/2
 def color(channel):page.wait_for_function(f"document.querySelector('#stage')?.getContext('2d').getImageData(50,40,1,1).data[{channel}]>220")
 def drag(id,dy,dx=0,release=True):
  x,y=point(id);page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+dx,y+dy,steps=8)
  if release:page.mouse.up()
 def undo():page.keyboard.press('Meta+z')
 page.goto(f'http://127.0.0.1:5174/#/studio?project={PID}');page.wait_for_selector('.stage-loading',state='hidden',timeout=60000);color(2)
 expect(page.locator('.ly-lane')).to_have_count(2)
 dy=point('newer')[1]-point('older')[1]
 drag('older',dy,release=False);expect(page.locator('.ly-order-drop')).to_have_text('In front');color(0)
 checks.append('Preview changes to older take during vertical drag')
 page.mouse.up();expect(clip('older')).to_be_visible();save()
 assert next(x for x in saved['layers'] if x['id']=='older')==original['layers'][0]
 assert [x['id'] for x in saved['layers']]==['newer','later','older','text']
 assert point('older')[1]<point('newer')[1]
 checks.append('Drop changes display order without touching subframe timing, source trims, keys or transforms')
 undo();color(2);save();assert saved['layers']==original['layers'];checks.append('One undo restores the full original stack')
 page.keyboard.press('Meta+Shift+z');color(0);save();page.reload();page.wait_for_selector('.stage-loading',state='hidden',timeout=60000);color(0);checks.append('Order survives save and reload')
 # Downward motion can put the current front take behind the newer one again.
 dy=point('newer')[1]-point('older')[1];drag('older',dy);color(2);save();assert saved['layers']==original['layers'];checks.append('Dragging down sends a take behind')
 # Time editing still repacks and preserves order without fixed track assignments.
 body=page.locator('.ly-lane .tl-body').first.bounding_box();pps=body['width']/saved['duration']
 drag('newer',0,8*pps);expect(page.locator('.ly-lane')).to_have_count(1);save()
 assert next(x for x in saved['layers'] if x['id']=='newer')['start']==8
 assert next(x for x in saved['layers'] if x['id']=='older')==original['layers'][0]
 checks.append('Consecutive clips compact into a single row after moving apart')
 page.screenshot(path=str(OUT/'condensed.png'))
 # Moving back creates only the necessary overlap row, and remains a single undo step.
 undo();expect(page.locator('.ly-lane')).to_have_count(2);color(2)
 # Cancel restores both the ordering and time, even after live preview has changed.
 before=copy.deepcopy(saved);save();before=copy.deepcopy(saved)
 dy=point('newer')[1]-point('older')[1];drag('older',dy,dx=20,release=False)
 clip('older').dispatch_event('pointercancel',{'pointerId':1});page.mouse.up();save();assert saved['layers']==before['layers'];checks.append('Pointer cancellation restores timing and display order')
 # Keyboard alternative for a focused clip.
 clip('older').focus();page.keyboard.press('Alt+ArrowUp');save();assert [l['id'] for l in saved['layers']].index('older')>[l['id'] for l in saved['layers']].index('newer');color(0)
 checks.append('Focused clips can move forward with Alt+Up')
 page.screenshot(path=str(OUT/'reordered.png'))
 # The exported composition follows the same authored order as the live viewer.
 page.goto(f'http://127.0.0.1:5174/#/render?project={PID}&layer=composite');page.wait_for_function('window.__typeset')
 pixel=page.evaluate('''async()=>{const a=window.__typeset;await a.ready;await a.renderFrame(24);return [...document.querySelector('#stage').getContext('2d').getImageData(50,40,1,1).data]}''');assert pixel[0]>220 and pixel[2]<10,pixel
 checks.append('Export renders the same display order')
 assert not errors,errors;report=dict(passed=len(checks),checks=checks,errors=errors);(OUT/'checks.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));b.close()
