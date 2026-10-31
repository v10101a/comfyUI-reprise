"""Tile PNGs into one contact sheet: sheet.py out.jpg a.png b.png ... (row width 2 by default, --cols=N)"""
import sys
from PIL import Image
args=[a for a in sys.argv[1:] if not a.startswith('--')]; cols=int(next((a[7:] for a in sys.argv if a.startswith('--cols=')),2))
out,paths=args[0],args[1:]
ims=[Image.open(p).convert('RGB') for p in paths]
w=max(i.width for i in ims)//2;h=max(i.height for i in ims)//2
ims=[i.resize((w,h)) for i in ims]
rows=(len(ims)+cols-1)//cols
s=Image.new('RGB',(w*cols+4*(cols-1),h*rows+4*(rows-1)),'magenta')
for k,i in enumerate(ims):s.paste(i,((k%cols)*(w+4),(k//cols)*(h+4)))
s.save(out,quality=88);print(out)
