"""Board gestures, persistence, real input assignment and isolation from the composition, with local API fixtures."""
import base64,copy,json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
OUT=Path('outputs/progress/reference-board');OUT.mkdir(parents=True,exist_ok=True)
BASE=os.environ.get('TYPESET_UI_URL','http://127.0.0.1:5174');PID='board-qa'
def image(color):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240"><rect width="240" height="240" fill="{color}"/><circle cx="120" cy="85" r="42" fill="#eee"/><rect x="62" y="130" width="116" height="110" rx="30" fill="#eee"/></svg>'
    return 'data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()
def card(id,x,y,kind='asset',**kw):return dict(id=id,x=x,y=y,kind=kind,w=220,h=224,title=id,role='reference',**kw)
saved=dict(version=1,id=PID,name='Board study',width=640,height=360,fps=24,duration=5,media={},analysis={},shots=[],surfaces=[],grade=None,
    style=dict(fontFamily='Inter',fontWeight=700,fontSize=.1,fill='#ffffff',align='center'),look=dict(id='default'),words=[],
    assets=[dict(id='face',kind='image',path=image('#9c83c4'),name='Character'),dict(id='coat',kind='image',path=image('#6f9d94'),name='Wardrobe')],
    layers=[dict(id='shot',kind='media',name='Angel motion',assetId='face',start=0,**{'in':0},out=5,transform=dict(scale=1.1),generation=dict(workflowId='wf',workflows={'wf':dict(inputs={'prompt':'Night scene'},sources={'face':'face'})}))],
    board=dict(cards=[dict(id='group',kind='group',title='Direction A',role='reference',x=0,y=0,w=620,h=440),card('Character',30,80,assetId='face'),card('Wardrobe',300,80,assetId='coat'),card('Movement',680,80,'note',text='Quiet movement')]))
initial=copy.deepcopy(saved)
wf=dict(id='wf',name='Character + wardrobe',nodes=4,source='file',missing=[],missingModels=[],output=dict(node='4',type='image'),candidates=dict(inputs=[],outputs=[]),
    inputs=dict(face=dict(node='1',field='image',role='media',kind='comfy_input_path',media='image',title='Character image'),
                costume=dict(node='2',field='image',role='media',kind='comfy_input_path',media='image',title='Wardrobe image'),
                prompt=dict(node='3',field='text',role='prompt',kind='string',title='Direction',default='Night scene')))
errors=[];writes=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport=dict(width=1440,height=1050))
    page.on('pageerror',lambda e:errors.append(str(e)))
    def route(r):
        global saved
        req=r.request;path=req.url.split('/api/',1)[-1].split('?',1)[0]
        if path==f'projects/{PID}':
            if req.method=='PUT':saved=req.post_data_json;writes.append(copy.deepcopy(saved))
            r.fulfill(json=saved)
        elif path=='projects':r.fulfill(json=[saved])
        elif path=='workflows':r.fulfill(json=[wf])
        elif path=='health':r.fulfill(json=dict(comfyui=True,remote=None))
        elif path=='jobs':r.fulfill(json=[])
        elif path=='session':r.fulfill(json=dict(projectId=PID))
        else:r.fulfill(status=404,json=dict(detail='Disabled in board QA'))
    page.route('**/api/**',route)
    page.goto(f'{BASE}/#/studio?project={PID}');page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    page.get_by_role('button',name='Board',exact=True).click();expect(page.get_by_role('region',name='Reference board')).to_be_visible()
    def save():
        with page.expect_response(lambda r:r.request.method=='PUT' and PID in r.url):page.locator('.s-save').click()
    # A group and both contained images move as one; the note outside remains fixed.
    head=page.locator('[data-board-card="group"] .rb-card-head');box=head.bounding_box()
    page.mouse.move(box['x']+60,box['y']+12);page.mouse.down();page.mouse.move(box['x']+140,box['y']+62,steps=8);page.mouse.up();save()
    by={c['id']:c for c in saved['board']['cards']}
    assert (by['group']['x'],by['group']['y'])==(80,50),by
    assert (by['Character']['x'],by['Character']['y'])==(110,130)
    assert (by['Wardrobe']['x'],by['Wardrobe']['y'])==(380,130)
    assert by['Movement']['x']==680
    assert saved['layers']==initial['layers'],'Board move changed composition'
    # Roles only organize. A deliberate input assignment changes generation.
    page.locator('[data-board-card="Wardrobe"] .rb-card-title').click()
    page.get_by_label('Reference role',exact=True).select_option('wardrobe');save()
    assert saved['layers'][0]['generation']['workflows']['wf']['sources']=={'face':'face'}
    page.get_by_label('Workflow input',exact=True).select_option('costume')
    page.get_by_role('button',name='Use as reference',exact=True).click();save()
    assert saved['layers'][0]['generation']['workflows']['wf']['sources']=={'face':'face','costume':'coat'}
    page.get_by_role('button',name='Open generation & takes ↗',exact=True).click()
    expect(page.locator('.wf-panel').get_by_label('Reference: Wardrobe image',exact=True)).to_have_value('coat')
    page.get_by_role('button',name='Board',exact=True).click()
    # Notes explicitly append to a prompt, once; source URLs never execute as script URLs.
    page.locator('[data-board-card="Movement"] .rb-card-title').click()
    page.get_by_label('Board note',exact=True).fill('Hair moves in a soft breeze. Mouth stays closed.')
    page.get_by_role('button',name='Add note to prompt',exact=True).click();save()
    assert saved['layers'][0]['generation']['workflows']['wf']['inputs']['prompt']=='Night scene\n\nHair moves in a soft breeze. Mouth stays closed.'
    page.get_by_label('Reference source link',exact=True).fill('javascript:alert(1)')
    expect(page.get_by_role('link',name='Open source ↗',exact=True)).to_have_count(0)
    page.get_by_label('Reference source link',exact=True).fill('https://kinopio.club/')
    expect(page.get_by_role('link',name='Open source ↗',exact=True)).to_have_attribute('href','https://kinopio.club/')
    page.screenshot(path=str(OUT/'board.png'))
    page.get_by_role('button',name='Zoom in board',exact=True).click()
    expect(page.locator('.rb-zoom>span')).to_have_text('125%')
    # Remove only a board card; the source media and workflow binding survive. Undo restores its position.
    page.locator('[data-board-card="Wardrobe"] .rb-card-title').click()
    page.get_by_role('button',name='Remove card from board',exact=True).click();save()
    assert len(saved['assets'])==2 and saved['layers'][0]['assetId']=='face'
    assert saved['layers'][0]['generation']['workflows']['wf']['sources']['costume']=='coat'
    page.get_by_label('Board canvas',exact=True).focus();page.keyboard.press('Meta+z');save()
    assert len(saved['board']['cards'])==4
    page.reload();page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    page.get_by_role('button',name='Board',exact=True).click()
    expect(page.locator('.rb-zoom>span')).to_have_text('125%')
    expect(page.locator('[data-board-card="Wardrobe"]')).to_be_visible()
    # Creating/deleting with board keyboard shortcuts cannot delete a scene layer.
    page.get_by_role('button',name='+ Note',exact=True).click()
    page.get_by_label('Card title',exact=True).fill('New thought');save()
    page.get_by_label('Board canvas',exact=True).focus();page.keyboard.press('Backspace');save()
    assert len(saved['layers'])==1 and len(saved['board']['cards'])==4
    assert not errors,errors
    report=dict(checks=11,projectWrites=len(writes),consoleErrors=errors,compositionSource=saved['layers'][0]['assetId'],sources=saved['layers'][0]['generation']['workflows']['wf']['sources'])
    (OUT/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));browser.close()
