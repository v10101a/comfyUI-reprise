"""Build SCHEMA v2 §B occupancy.json from a project's matte PNGs (read-only on data/).
Usage: server/.venv/bin/python apps/web/scripts/make_occupancy_fixture.py <project-id> [...]
Writes apps/web/public/fixtures/<id>/occupancy.json. Stopgap until the server's matte job writes analysis/occupancy.json.
"""
import base64, json, sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parents[3]
COLS, ROWS = 32, 18
for pid in sys.argv[1:]:
    proj = json.loads((ROOT / 'data/projects' / pid / 'project.json').read_text())
    matte = ROOT / 'data/projects' / pid / proj['analysis']['matte']
    cols, rows = (COLS, ROWS) if proj['width'] >= proj['height'] else (ROWS, COLS)
    frames = []
    for png in sorted(matte.glob('fg_*.png')):
        a = np.asarray(Image.open(png).convert('RGBA'))[:, :, 3].astype(np.float32) / 255
        h, w = a.shape
        ys = np.linspace(0, h, rows + 1).astype(int); xs = np.linspace(0, w, cols + 1).astype(int)
        grid = np.array([[a[ys[r]:ys[r+1], xs[c]:xs[c+1]].mean() for c in range(cols)] for r in range(rows)])
        frames.append(base64.b64encode(np.round(grid * 255).astype(np.uint8).tobytes()).decode())
    out = ROOT / 'apps/web/public/fixtures' / pid / 'occupancy.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'fps': proj['fps'], 'cols': cols, 'rows': rows, 'step': 1, 'frames': frames}))
    print(out, len(frames), 'frames', cols, 'x', rows)
