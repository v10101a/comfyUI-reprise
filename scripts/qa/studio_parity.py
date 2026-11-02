# Studio stage canvas vs #/render (the demo's renderer) at the same frames: native canvas pixels, diff stats.
# Usage: server/.venv/bin/python scripts/qa/studio_parity.py <project_id> <out_prefix> 0,40   (dev server :5174)
import sys,base64,io
from playwright.sync_api import sync_playwright
import numpy as np, cv2
PID=sys.argv[1]; OUT=sys.argv[2]; STEPS=[int(x) for x in sys.argv[3].split(',')]  # extra frames after the studio's start frame
def png(pg,sel):
    d=pg.evaluate(f"()=>document.querySelector('{sel}').toDataURL('image/png')")
    return cv2.imdecode(np.frombuffer(base64.b64decode(d.split(',')[1]),np.uint8),cv2.IMREAD_COLOR)
with sync_playwright() as pw:
    b=pw.chromium.launch()
    st=b.new_page(viewport={'width':1600,'height':1000});st.route_web_socket('**',lambda s:None)
    st.goto(f'http://127.0.0.1:5174/#/studio?project={PID}');st.wait_for_timeout(9000)
    sel='.stage-wrap canvas'
    import json,urllib.request
    fps=json.load(urllib.request.urlopen(f'http://127.0.0.1:8787/api/projects/{PID}'))['fps']
    start=round(.8*fps)  # the studio opens on this frame
    rd=b.new_page(viewport={'width':1600,'height':1000});rd.route_web_socket('**',lambda s:None)
    rd.goto(f'http://127.0.0.1:5174/#/render?project={PID}&layer=composite');rd.wait_for_function('window.__typeset!==undefined');rd.evaluate('()=>window.__typeset.ready')
    cur=0
    for k in STEPS:
        st.locator('body').click(position={'x':5,'y':5})
        for _ in range(k-cur): st.keyboard.press('ArrowRight')
        cur=k; st.wait_for_timeout(5000)
        a=png(st,sel); rd.evaluate('f=>window.__typeset.renderFrame(f)',start+k); b2=png(rd,'#stage')
        if a.shape!=b2.shape: a=cv2.resize(a,(b2.shape[1],b2.shape[0]))
        d=np.abs(a.astype(int)-b2.astype(int)).sum(2)
        print(f'frame {start+k}: mean {d.mean():.2f}  px>30 {(d>30).mean()*100:.2f}%  studio mean BGR {a.reshape(-1,3).mean(0).round(1)} render {b2.reshape(-1,3).mean(0).round(1)}')
        cv2.imwrite(f'{OUT}_{start+k}.jpg',np.hstack([a,b2]))
    b.close()
