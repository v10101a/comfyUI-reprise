#!/usr/bin/env python3
"""Produce labeled, unretouched contact sheets from measured experiment outputs."""
from pathlib import Path
import subprocess
from PIL import Image, ImageOps, ImageDraw, ImageFont
root=Path(__file__).resolve().parents[2]
font=ImageFont.truetype(str(root/'apps/web/public/fonts/SpaceMono-Regular.ttf'),15)
out=root/'docs/eval/contact-sheets'; out.mkdir(parents=True,exist_ok=True)
base=root/'docs/eval/current'
for video in base.rglob('*.mp4'):
    for i in [0,12,24,36,48]:
        frame=video.with_name(video.stem+f'_f{i:03}.png')
        if not frame.exists():
            subprocess.run(['ffmpeg','-v','error','-y','-i',str(video),'-vf',f'select=eq(n\\,{i})','-fps_mode','vfr','-frames:v','1',str(frame)],check=True)

def sheet(name, items, columns):
    if not items:return
    cw,ch=384,260
    image=Image.new('RGB',(cw*columns,ch*((len(items)+columns-1)//columns)), '#17191b')
    d=ImageDraw.Draw(image)
    for i,(label,path) in enumerate(items):
        x,y=i%columns*cw,i//columns*ch
        with Image.open(path) as src:
            tile=ImageOps.contain(src.convert('RGB'),(cw-12,ch-40))
            image.paste(tile,(x+(cw-tile.width)//2,y+32+(ch-40-tile.height)//2))
        d.text((x+8,y+8),label,font=font,fill='#e4e9de')
    image.save(out/(name+'.jpg'),quality=92)

for tag in ['i2v_letters','morph_letters','spatial_upscale','ltx13b_gguf']:
    sheet(tag,[(p.stem.split('_')[-1],p) for p in sorted((base/tag).glob('*_f*.png'))],5)
for model in ['klein4b_t2i','zimage_t2i']:
    items=[]
    for name in ['neon','louder','stay','holdon','forever','echo']:
        files=list((base/(model+'_'+name)).glob('*.png'))
        if files:items.append((name,files[0]))
    sheet(model,items,3)
items=[('input wall',root/'docs/eval/plates/wall_1024x576.png')]
items.extend(('Klein edit',p) for p in (base/'klein4b_edit_wall').glob('*.png'))
items.extend(('Qwen edit',p) for p in (base/'qwen_edit_wall').glob('*.png'))
sheet('frame-edit',items,3)
print(out)
