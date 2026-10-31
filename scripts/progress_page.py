#!/usr/bin/env python3
"""Build outputs/progress/index.html from outputs/progress/tasks.json.

Local-only tracker: media are linked relatively (open the file in a browser, nothing is uploaded).
Globs are relative to outputs/; newest files first. `--watch N` rebuilds every N seconds.
"""
import argparse, glob, html, json, os, time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "outputs")
PAGE = os.path.join(OUT, "progress", "index.html")
STATUS = {"running": ("running", "#2e00fd"), "you": ("needs you", "#d1001f"), "done": ("done", "#2e7d32")}
VIDEO, AUDIO = (".mp4", ".webm", ".mov"), (".wav", ".flac", ".mp3")


def find(patterns, limit):
    seen, hits = set(), []
    for pat in patterns:
        for p in glob.glob(os.path.join(OUT, pat), recursive=True):
            p = os.path.normpath(p)
            if p not in seen and os.path.isfile(p):
                seen.add(p); hits.append(p)
    hits.sort(key=os.path.getmtime, reverse=True)
    return hits[:limit]


def tile(path):
    rel = html.escape(os.path.relpath(path, os.path.dirname(PAGE)))
    name = html.escape(os.path.relpath(path, ROOT))
    when = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%H:%M")
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO:
        el = f'<video src="{rel}" controls muted loop preload="metadata"></video>'
    elif ext in AUDIO:
        el = f'<div class="aud"><audio src="{rel}" controls preload="none"></audio></div>'
    elif ext in (".txt", ".md", ".json"):
        el = f'<a class="doc" href="{rel}">{html.escape(os.path.basename(path))}</a>'
    else:
        el = f'<a href="{rel}"><img src="{rel}" loading="lazy"></a>'
    return f'<figure>{el}<figcaption title="{name}">{html.escape(os.path.basename(path))} · {when}</figcaption></figure>'


def build():
    tasks = json.load(open(os.path.join(OUT, "progress", "tasks.json")))
    order = {"you": 0, "running": 1, "done": 2}
    tasks.sort(key=lambda t: order.get(t.get("status"), 3))
    cards = []
    for t in tasks:
        label, color = STATUS.get(t.get("status"), (t.get("status", ""), "#5e5e5e"))
        media = find(t.get("media", []), t.get("limit", 6))
        files = find(t.get("files", []), 6)
        tiles = "".join(tile(p) for p in media + files)
        note = f'<p>{html.escape(t["note"])}</p>' if t.get("note") else ""
        cards.append(f'<section><header><h2>{html.escape(t["title"])}</h2>'
                     f'<span class="st" style="--c:{color}">{label}</span></header>{note}'
                     f'<div class="grid">{tiles}</div></section>')
    now = datetime.now().strftime("%a %H:%M")
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Typeset progress</title><meta http-equiv="refresh" content="60">
<style>
:root{{--bg:#c7c7c7;--p:#d2d2d2;--tx:#1e1e1e;--mut:#5e5e5e;--ln:#0000001f}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1b1f11;--p:#262b1a;--tx:#e2e2e2;--mut:#9a9f90;--ln:#ffffff1f}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 Inter,system-ui,sans-serif}}
main{{max-width:1200px;margin:0 auto;padding:24px 16px 64px}}
.top{{display:flex;align-items:baseline;justify-content:space-between;border-bottom:1px solid var(--ln);padding-bottom:12px}}
h1{{font:italic 400 28px Newsreader,Georgia,serif;margin:0;color:#2e00fd}}.top span{{color:var(--mut);font:12px ui-monospace,monospace}}
section{{padding:20px 0;border-bottom:1px solid var(--ln)}}
header{{display:flex;align-items:center;gap:12px}}h2{{font:500 18px Newsreader,Georgia,serif;margin:0}}
.st{{font-size:12px;padding:2px 8px;border-radius:999px;border:1px solid var(--c);color:var(--c)}}
p{{margin:6px 0 0;color:var(--mut)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin-top:12px}}
figure{{margin:0;background:var(--p);padding:6px}}img,video{{display:block;width:100%;max-height:360px;object-fit:contain;background:#0002}}
.aud{{padding:16px 0}}audio{{width:100%}}.doc{{display:block;padding:16px 4px;color:#2e00fd}}
figcaption{{font:11px ui-monospace,monospace;color:var(--mut);margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
</style></head><body><main><div class="top"><h1>typeset · progress</h1><span>updated {now}</span></div>
{''.join(cards)}</main></body></html>"""
    tmp = PAGE + ".tmp"
    open(tmp, "w").write(doc)
    os.replace(tmp, PAGE)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=int, default=0)
    a = ap.parse_args()
    while True:
        build()
        if not a.watch:
            print(PAGE); break
        time.sleep(a.watch)
