"""Rebuild the two App Mode templates from named API inputs and current node schemas.

Use the ComfyUI Python environment (torch/Pillow/OpenCV) and a running ComfyUI for core node schemas:
  ~/ComfyUI/.venv/bin/python scripts/build_typeset_app_workflows.py --comfy http://127.0.0.1:8188
Or supply a saved /object_info response with --object-info. Typeset schemas always come from this
checkout, so a server that has not restarted cannot silently drop new controls or reorder their values.
"""
import argparse
import copy
import importlib
import json
import sys
import types
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes_dev/typeset_nodes"
WF = ROOT / "workflows"
LAYOUT = {
    1: (40, 100, 310, 280), 2: (400, 100, 260, 110), 13: (40, 420, 310, 180),
    3: (710, 100, 340, 320), 12: (1110, 100, 380, 120),
    4: (710, 500, 400, 360), 5: (1170, 500, 340, 200), 6: (1170, 760, 340, 150),
    7: (40, 970, 330, 820), 8: (430, 970, 300, 300),
    9: (1600, 100, 400, 290), 10: (2060, 100, 280, 160), 11: (2400, 100, 300, 160),
}
APP_LABELS = {("1", "file"): "Footage", ("13", "audio"): "Song excerpt", ("4", "lyrics"): "Exact lyrics",
              ("7", "preset"): "Text look", ("8", "grade"): "Footage grade",
              ("9", "voice"): "Voice response", ("9", "flow"): "Motion response"}
APP_HINTS = {("1", "file"): "Sets the output length.",
             ("13", "audio"): "Match the footage; starts at 0.",
             ("4", "lyrics"): "One phrase per line.",
             ("9", "voice"): "Type reacts to the singer.",
             ("9", "flow"): "Type reacts to scene movement."}


def schemas(core):
    info = copy.deepcopy(core)
    # Import just the node modules, without mounting the Studio or starting a JobManager.
    package = "_typeset_app_workflow_nodes"
    pkg = types.ModuleType(package)
    pkg.__path__ = [str(PACK)]
    sys.modules.setdefault(package, pkg)
    for name in ("looks", "lyric_align", "voice_field", "flow_field", "render_node", "matte_refine"):
        module = importlib.import_module(f"{package}.{name}")
        for key, cls in module.NODE_CLASS_MAPPINGS.items():
            inputs = cls.INPUT_TYPES()
            info[key] = {"input": inputs, "input_order": {k: list(v) for k, v in inputs.items()},
                         "output": list(cls.RETURN_TYPES), "output_name": list(getattr(cls, "RETURN_NAMES", cls.RETURN_TYPES))}
    return info


def is_link(value):
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int)


def is_widget(kind, meta):
    return (isinstance(kind, list) or kind in ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO")) and not meta.get("forceInput")


def default_value(kind, meta):
    return meta.get("default", kind[0] if isinstance(kind, list) and kind else None)


def app_graph(base, info, separate_song=False):
    graph = copy.deepcopy(base)
    # The render node takes original frames plus grade settings. Do not grade an unused frame batch.
    graph["8"]["class_type"] = "TypesetGradeSettings"
    graph["8"]["inputs"] = {k: v for k, v in graph["8"]["inputs"].items()
                              if k in info["TypesetGradeSettings"]["input"]["required"]}
    graph["9"]["inputs"]["grade_json"] = ["8", 0]
    if separate_song:
        graph["13"] = {"class_type": "LoadAudio", "inputs": {"audio": "typeset_neon_rain.flac"}, "_meta": {"title": "your song"}}
        for nid in ("4", "5", "10"):
            graph[nid]["inputs"]["audio"] = ["13", 0]
        graph["11"]["inputs"]["filename_prefix"] = "typeset/app_separate_song"
    for nid, node in graph.items():
        spec = info[node["class_type"]]
        for key, entry in spec["input"].get("required", {}).items():
            if key in node["inputs"]:
                continue
            kind, meta = entry[0], entry[1] if len(entry) > 1 else {}
            if not is_widget(kind, meta):
                raise ValueError(f"Missing required connection: {nid}.{key}")
            node["inputs"][key] = default_value(kind, meta)
    return graph


def ui_workflow(graph, info, separate_song=False):
    nodes, links, incoming, outgoing = [], [], {}, {}
    for nid, node in graph.items():
        for name, value in node["inputs"].items():
            if not is_link(value):
                continue
            src, slot = value
            kind = info[graph[src]["class_type"]]["output"][slot]
            lid = len(links) + 1
            links.append([lid, int(src), slot, int(nid), None, kind])
            incoming.setdefault(nid, {})[name] = lid
            outgoing.setdefault((src, slot), []).append(lid)
    for order, (nid, node) in enumerate(graph.items()):
        cls, values = node["class_type"], node["inputs"]
        spec = info[cls]
        req, opt = spec["input"].get("required", {}), spec["input"].get("optional", {})
        fields = {**req, **opt}
        names = list(spec.get("input_order", {}).get("required", req)) + list(spec.get("input_order", {}).get("optional", opt))
        inputs, widgets = [], []
        for name in names:
            entry = fields[name]
            kind, meta = entry[0], entry[1] if len(entry) > 1 else {}
            widget = is_widget(kind, meta)
            link = incoming.get(nid, {}).get(name)
            if widget:
                value = values.get(name, default_value(kind, meta))
                widgets.append(None if is_link(value) else value)
                if meta.get("control_after_generate"):
                    widgets.append("fixed")
                if any(meta.get(k) for k in ("video_upload", "audio_upload", "image_upload")):
                    widgets.append(None)
            label = APP_LABELS.get((nid, name))
            if link or not widget or label:
                port = {"name": name, "type": "COMBO" if isinstance(kind, list) else kind, "link": link}
                if label:
                    port["label"] = label
                if widget:
                    port["widget"] = {"name": name}
                if link:
                    links[link - 1][4] = len(inputs)
                inputs.append(port)
        outputs = [{"name": name, "type": kind, "links": outgoing.get((nid, i), []), "slot_index": i}
                   for i, (name, kind) in enumerate(zip(spec.get("output_name", spec["output"]), spec["output"]))]
        x, y, w, h = LAYOUT[int(nid)]
        nodes.append({"id": int(nid), "type": cls, "title": node.get("_meta", {}).get("title", cls),
                      "pos": [x, y], "size": [w, h], "flags": {}, "order": order, "mode": 0,
                      "inputs": inputs, "outputs": outputs, "widgets_values": widgets, "properties": {"Node name for S&R": cls}})
    note = ("# Words in your shot\n\nChoose footage" + (" and a song" if separate_song else " with audio") +
            ", paste the matching lyrics, choose a look, then Run. The output keeps the original song.\n\n" +
            ("Use a song excerpt that starts where the footage should start; this template aligns both at time zero. "
             "The output lasts as long as the footage.\n\n" if separate_song else "") +
            "App Mode exposes the everyday choices. Graph view exposes lettering, matte and analysis controls. "
            "Grade settings feeds JSON to TypesetRender, which applies the grade once. "
            "Align Lyrics shares its vocal stem with Voice Field.\n\n"
            "Needs Reprise nodes, ComfyUI-RMBG (BiRefNet), HDemucs + MMS_FA weights for lyrics, and a built Reprise Studio + Playwright "
            "for full-quality rendering. Auto renderer reports when it falls back to draft.")
    nodes.append({"id": 99, "type": "MarkdownNote", "pos": [1600, 500], "size": [580, 360], "flags": {},
                  "order": len(nodes), "mode": 0, "inputs": [], "outputs": [], "widgets_values": [note], "properties": {}})
    exposed = [["1", "file"]] + ([["13", "audio"]] if separate_song else []) + [
        ["4", "lyrics"], ["7", "preset"], ["8", "grade"], ["9", "voice"], ["9", "flow"]]
    exposed = [pair + ([{"description": APP_HINTS[tuple(pair)]}] if tuple(pair) in APP_HINTS else []) for pair in exposed]
    return {"last_node_id": 99, "last_link_id": len(links), "nodes": nodes, "links": links, "groups": [], "config": {},
            "extra": {"ds": {"scale": .45, "offset": [70, 40]}, "linearMode": True,
                      "linearData": {"inputs": exposed, "outputs": ["11"]}}, "version": .4}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy", default="http://127.0.0.1:8188")
    parser.add_argument("--object-info", type=Path)
    args = parser.parse_args()
    core = json.loads(args.object_info.read_text()) if args.object_info else json.load(urlopen(args.comfy.rstrip('/') + '/object_info', timeout=60))
    info = schemas(core)
    base = json.loads((WF / "app_words_in_your_shot.api.json").read_text())
    for separate in (False, True):
        name = "words_in_your_shot" + ("_and_song" if separate else "")
        graph = app_graph(base, info, separate)
        ui = ui_workflow(graph, info, separate)
        files = [(WF / f"app_{name}.api.json", graph), (WF / "showcase" / f"typeset_app_{name}.json", ui),
                 (PACK / "example_workflows" / ("Reprise - " + name.replace('_', ' ') + ".json"), ui)]
        for path, data in files:
            path.write_text(json.dumps(data, indent=2) + "\n")
            print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
