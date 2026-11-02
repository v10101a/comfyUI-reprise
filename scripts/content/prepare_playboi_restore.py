"""Inventory earlier Playboi boards and their finished clips for Studio recovery."""
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps

OUT = Path('outputs/songs/playboi/reviews/earlier_library')
OUT.mkdir(parents=True, exist_ok=True)
RAW = Path('outputs/songs/viola-refs/shots/raw')
items = []

def add(name, path, title, layer='playboi-shot-01', workflow=None):
    recipe = {'engine': 'MiniMax H3 · earlier Playboi', 'archiveSource': str(path)}
    if workflow and workflow.exists():
        g = json.loads(workflow.read_text())
        recipe.update(workflow=str(workflow), prompt=g.get('6', {}).get('inputs', {}).get('prompt'),
                      seed=g.get('7', {}).get('inputs', {}).get('noise_seed'))
    rp = OUT / (name + '.recipe.json'); rp.write_text(json.dumps(recipe, indent=2))
    items.append(dict(name=name, title=title, file=str(path), run=str(rp), layer=layer))

frames = dict(pb_p1_bedjump=20, pb_p3_hallrun=20, pb_p4_cart=8, pb_p2_feathers=34,
              pb3_s1_mirror=20, pb3_s2_booth_deadpan=20, pb3_s5_motelneon=20, pb3_s7_pool=8)
frames.update({j['name']:20 for j in json.loads(Path('outputs/progress/video_takeover/backups/pb4.json').read_text())})
for name, frame in frames.items():
    folder = RAW / name
    files = sorted(folder.glob(f'*_f{frame:03d}_*.png'))
    if not files:
        files = sorted(folder.glob('*.png'))
    assert files, name
    title = 'Earlier · ' + name.split('_', 2)[-1].replace('_', ' ')
    add(name, files[0], title, workflow=folder/'workflow.json')
for place in ('booth', 'pool', 'motel'):
    name = f'pb5_{place}_natural_lips'
    add(name, RAW.parent/'edited'/f'{name}.png', f'Earlier · {place} / corrected still')
for name, title, layer in [('pb5_booth_deadpan','Booth / deadpan','playboi-shot-01'),
                           ('pb5_booth_smirk','Booth / smirk','playboi-shot-03'),
                           ('pb5_pool_smirk','Pool / smirk','playboi-shot-07'),
                           ('pb5_motel_wind','Motel / wind','playboi-shot-05')]:
    folder = Path('outputs/songs/playboi/clips')/name
    add(name, folder/'review.mp4', 'Earlier take · '+title, layer, folder/'workflow.json')
manifest = dict(song='playboi', id='pb-earlier-library', title='Earlier Playboi · boards & finished takes', columns=4, items=items)
(OUT/'restore.json').write_text(json.dumps(manifest, indent=2))
cols, cellw, cellh = 4, 320, 210
sheet = Image.new('RGB', (cols*cellw, ((len(items)+cols-1)//cols)*cellh), '#161616')
draw = ImageDraw.Draw(sheet)
for i,item in enumerate(items):
    path = Path(item['file'])
    if path.suffix == '.mp4':
        thumb = OUT / (item['name']+'.jpg')
        subprocess.run(['ffmpeg','-v','error','-y','-ss','1','-i',str(path),'-frames:v','1',str(thumb)],check=True)
        path = thumb
    im = ImageOps.contain(Image.open(path).convert('RGB'), (cellw,180))
    x,y=(i%cols)*cellw,(i//cols)*cellh
    sheet.paste(im,(x+(cellw-im.width)//2,y))
    draw.text((x+8,y+184),item['title'],fill='white')
sheet.save(OUT/'earlier_playboi.jpg',quality=92)
print(json.dumps({'items':len(items),'stills':sum(Path(i['file']).suffix=='.png' for i in items),'clips':4,'manifest':str(OUT/'restore.json')}))
