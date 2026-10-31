"""Generate the Typeset analysis workflows from one spec:

  workflows/{occupancy,surface_track,reframe,beats,align}.api.json + .inputs.json   (server, via the Comfy SDK)
  workflows/showcase/typeset_analysis.json        (UI format: drag into ComfyUI)
  workflows/showcase/typeset_analysis.api.json    (same graph, API format, for headless runs)

UI-format widget order comes from the live ComfyUI /object_info, so run this against a ComfyUI that has
typeset_nodes loaded:   server/.venv/bin/python scripts/build_typeset_workflows.py [--comfy http://127.0.0.1:8188]
"""
import argparse
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / "workflows"

# ---- server workflows (API format) ----------------------------------------------------------

def save_api(name: str, graph: dict, sidecar: dict) -> None:
    (WF / f"{name}.api.json").write_text(json.dumps(graph, indent=2) + "\n")
    (WF / f"{name}.inputs.json").write_text(json.dumps({"workflow": f"{name}.api.json", **sidecar}, indent=2) + "\n")


def server_workflows() -> None:
    save_api("occupancy", {
        "1": {"class_type": "TypesetLoadImageSequence", "inputs": {"directory": "typeset/matte", "pattern": "fg_*.png", "max_frames": 0}},
        "2": {"class_type": "TypesetOccupancyGrid", "inputs": {"mask": ["1", 1], "fps": 24.0, "long_side_cells": 32, "preview_frames": 0}},
        "3": {"class_type": "SaveTextFile", "inputs": {"text": ["2", 0], "filename_prefix": "typeset/occupancy", "extension": "json", "pretty_json": False}},
    }, {
        "description": "Matte PNG sequence (alpha = subject) -> occupancy grid JSON (SCHEMA v2 §B).",
        "inputs": {
            "matte_dir": {"node": "1", "field": "directory", "kind": "comfy_input_path"},
            "fps": {"node": "2", "field": "fps", "kind": "float", "default": 24},
            "long_side_cells": {"node": "2", "field": "long_side_cells", "kind": "int", "default": 32},
        },
        "outputs": {"occupancy_json": {"node": "3", "type": "text"}},
    })
    save_api("surface_track", {
        "1": {"class_type": "LoadVideo", "inputs": {"file": "typeset/test/person_short.mp4"}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "TypesetLoadImageSequence", "inputs": {"directory": "", "pattern": "fg_*.png", "max_frames": 0}},
        "4": {"class_type": "TypesetPlanarTrack", "inputs": {
            "images": ["2", 0], "subject_mask": ["3", 1], "corners": "[[0.3,0.3],[0.7,0.3],[0.7,0.7],[0.3,0.7]]",
            "key_frame": 0, "fps": 24.0, "feature_region": 1.0, "min_confidence": 0.35, "smooth": 2, "preview_frames": 0}},
        "5": {"class_type": "SaveTextFile", "inputs": {"text": ["4", 0], "filename_prefix": "typeset/surface", "extension": "json", "pretty_json": False}},
    }, {
        "description": "Planar quad tracking (SCHEMA v2 §A). Caller normalizes the video to project size/fps; matte_dir '' = no subject mask.",
        "inputs": {
            "video": {"node": "1", "field": "file", "kind": "comfy_input_path"},
            "matte_dir": {"node": "3", "field": "directory", "kind": "string", "default": ""},
            "corners": {"node": "4", "field": "corners", "kind": "string"},
            "key_frame": {"node": "4", "field": "key_frame", "kind": "int", "default": 0},
            "fps": {"node": "4", "field": "fps", "kind": "float", "default": 24},
            "feature_region": {"node": "4", "field": "feature_region", "kind": "float", "default": 1.0},
            "min_confidence": {"node": "4", "field": "min_confidence", "kind": "float", "default": 0.35},
        },
        "outputs": {"surface_json": {"node": "5", "type": "text"}},
    })
    save_api("reframe", {
        "1": {"class_type": "TypesetReframeCrop", "inputs": {
            "aspect": "9:16", "fps": 24.0, "tracks_json": "{}", "surfaces_json": "", "width": 1920, "height": 1080,
            "frames": 0, "track_id": "person0", "focus_json": ""}},
        "2": {"class_type": "SaveTextFile", "inputs": {"text": ["1", 0], "filename_prefix": "typeset/crop", "extension": "json", "pretty_json": False}},
    }, {
        "description": "Subject-following virtual camera crop (SCHEMA v2 §C) from tracks.json (+ surface tracks, + focus regions the crop must contain).",
        "inputs": {
            "tracks_json": {"node": "1", "field": "tracks_json", "kind": "string"},
            "surfaces_json": {"node": "1", "field": "surfaces_json", "kind": "string", "default": ""},
            "aspect": {"node": "1", "field": "aspect", "kind": "string", "default": "9:16"},
            "fps": {"node": "1", "field": "fps", "kind": "float", "default": 24},
            "width": {"node": "1", "field": "width", "kind": "int"},
            "height": {"node": "1", "field": "height", "kind": "int"},
            "frames": {"node": "1", "field": "frames", "kind": "int"},
            "focus_json": {"node": "1", "field": "focus_json", "kind": "string", "default": ""},
        },
        "outputs": {"crop_json": {"node": "2", "type": "text"}},
    })
    save_api("beats", {
        "1": {"class_type": "LoadAudio", "inputs": {"audio": "typeset/test/song.wav"}},
        "2": {"class_type": "TypesetBeatGrid", "inputs": {"audio": ["1", 0], "beats_per_bar": 4, "section_seconds": 8.0}},
        "3": {"class_type": "SaveTextFile", "inputs": {"text": ["2", 0], "filename_prefix": "typeset/beats", "extension": "json", "pretty_json": True}},
        "4": {"class_type": "SaveImage", "inputs": {"images": ["2", 2], "filename_prefix": "typeset/beats"}},
    }, {
        "description": "Beats, downbeats and sections from audio (librosa) + waveform preview.",
        "inputs": {
            "audio": {"node": "1", "field": "audio", "kind": "comfy_input_path"},
            "beats_per_bar": {"node": "2", "field": "beats_per_bar", "kind": "int", "default": 4},
            "section_seconds": {"node": "2", "field": "section_seconds", "kind": "float", "default": 8.0},
        },
        "outputs": {"beats_json": {"node": "3", "type": "text"}, "preview": {"node": "4", "type": "image", "optional": True}},
    })
    save_api("align", {
        "1": {"class_type": "LoadAudio", "inputs": {"audio": "typeset/test/song.wav"}},
        "2": {"class_type": "TypesetAlignLyrics", "inputs": {
            "audio": ["1", 0], "lyrics": "", "separator": "hdemucs", "aligner": "mms_fa", "onset_window_ms": 50.0,
            "min_confidence": 0.05, "vocal_start": 0.0, "vocal_end": 0.0, "device": "cpu", "unload_models": True}},
        "3": {"class_type": "SaveTextFile", "inputs": {"text": ["2", 0], "filename_prefix": "typeset/align", "extension": "json", "pretty_json": True}},
        "4": {"class_type": "SaveImage", "inputs": {"images": ["2", 1], "filename_prefix": "typeset/align"}},
    }, {
        "description": "Known lyrics + song -> per-word timings by acoustic forced alignment (HDemucs vocal stem, MMS_FA CTC, vocal-onset refinement) + stem/spectrogram preview with word boxes.",
        "inputs": {
            "audio": {"node": "1", "field": "audio", "kind": "comfy_input_path"},
            "lyrics": {"node": "2", "field": "lyrics", "kind": "string"},
            "vocal_start": {"node": "2", "field": "vocal_start", "kind": "float", "default": 0.0},
            "vocal_end": {"node": "2", "field": "vocal_end", "kind": "float", "default": 0.0},
            "onset_window_ms": {"node": "2", "field": "onset_window_ms", "kind": "float", "default": 50.0},
            "device": {"node": "2", "field": "device", "kind": "string", "default": "cpu"},
        },
        "outputs": {"words_json": {"node": "3", "type": "text"}, "preview": {"node": "4", "type": "image", "optional": True}},
    })


# ---- showcase (one spec → UI + API) ------------------------------------------------------------

SHUTTER = "[[0.36,0.03],[0.50,0.08],[0.50,0.62],[0.36,0.68]]"
LYRICS = ("Walk me through the neon rain\nEvery sign repeats your name\n\nHold on, say it slow\n"
          "Louder than the radio\nHold on, let it show\nEvery word I know\n\nEvery word I know")

VHS = {"frame_rate": 24, "loop_count": 0, "format": "video/h264-mp4", "pix_fmt": "yuv420p", "crf": 19,
       "save_metadata": True, "trim_to_audio": False, "pingpong": False, "save_output": True}

# id: (class, {input: value | ("link", src_id, slot)}, (x, y), (w, h), group)
SHOW = {
    1: ("LoadVideo", {"file": "typeset_walk_night.mp4"}, (40, 120), (330, 360), "1"),
    2: ("GetVideoComponents", {"video": ("link", 1, 0)}, (400, 120), (260, 90), "1"),
    3: ("BiRefNetRMBG", {"image": ("link", 2, 0), "model": "BiRefNet_lite", "mask_blur": 0, "mask_offset": 0,
                         "invert_output": False, "refine_foreground": False, "background": "Alpha",
                         "background_color": "#222222", "sensitivity": 1.0, "unload_model": True},
        (400, 260), (300, 330), "2"),
    4: ("TypesetOccupancyGrid", {"mask": ("link", 3, 1), "images": ("link", 2, 0), "fps": ("link", 2, 2),
                                 "long_side_cells": 32, "preview_frames": 6}, (760, 120), (330, 170), "3"),
    5: ("PreviewImage", {"images": ("link", 4, 1)}, (1110, 120), (520, 330), "3"),
    6: ("MaskToTracks", {"mask": ("link", 3, 1), "fps": ("link", 2, 2), "label": "person", "track_id": "person0",
                         "threshold": 0.5, "min_area": 0.002, "smooth": 3, "max_side": 512}, (760, 520), (330, 250), "4"),
    7: ("TypesetReframeCrop", {"tracks_json": ("link", 6, 0), "images": ("link", 2, 0), "fps": ("link", 2, 2),
                               "aspect": "9:16", "surfaces_json": ("link", 9, 0), "width": 0, "height": 0, "frames": 0,
                               "track_id": "person0"}, (1110, 520), (330, 250), "4"),
    8: ("VHS_VideoCombine", {"images": ("link", 7, 1), "audio": ("link", 2, 1), **{**VHS, "filename_prefix": "typeset/showcase/reframe_9x16"}},
        (1460, 520), (300, 560), "4"),
    9: ("TypesetPlanarTrack", {"images": ("link", 2, 0), "subject_mask": ("link", 3, 1), "corners": SHUTTER,
                               "key_frame": 70, "fps": ("link", 2, 2), "feature_region": 1.0, "min_confidence": 0.35,
                               "smooth": 2, "preview_frames": 10000}, (760, 860), (330, 260), "5"),
    10: ("VHS_VideoCombine", {"images": ("link", 9, 1), **{**VHS, "filename_prefix": "typeset/showcase/surface_track"}},
         (1110, 860), (330, 440), "5"),
    11: ("PreviewAny", {"source": ("link", 9, 0)}, (1460, 1120), (300, 200), "5"),
    12: ("LoadAudio", {"audio": "typeset_neon_rain.flac"}, (40, 1400), (330, 140), "6"),
    13: ("TypesetBeatGrid", {"audio": ("link", 12, 0), "beats_per_bar": 4, "section_seconds": 8.0}, (400, 1400), (300, 120), "6"),
    14: ("PreviewImage", {"images": ("link", 13, 2)}, (760, 1400), (700, 200), "6"),
    15: ("PreviewAny", {"source": ("link", 13, 0)}, (1480, 1400), (300, 200), "6"),
    16: ("WhisperWords", {"audio": ("link", 12, 0), "model_size": "small", "language": "en", "lyrics": LYRICS,
                          "lyrics_as_prompt": True}, (400, 1640), (330, 260), "6"),
    17: ("PreviewAny", {"source": ("link", 16, 0)}, (760, 1640), (700, 260), "6"),
}

# Layout (x, y, w, h) — generous spacing because the frontend grows nodes to fit their widgets.
LAYOUT = {
    1: (40, 120, 360, 420), 2: (40, 600, 300, 100),
    3: (480, 120, 340, 440),
    4: (920, 120, 360, 240), 5: (1340, 120, 640, 420),
    6: (920, 680, 360, 320), 7: (1340, 680, 360, 340), 8: (1760, 680, 340, 640),
    9: (920, 1440, 360, 380), 10: (1340, 1440, 340, 640), 11: (1760, 1440, 380, 300),
    12: (40, 2180, 360, 160), 13: (480, 2180, 340, 160), 14: (920, 2180, 820, 300), 15: (1800, 2180, 380, 300),
    16: (480, 2540, 360, 380), 17: (920, 2540, 1260, 380),
}
NOTE_POS = (40, 760, 380, 1300)

GROUPS = {
    "1": ("1 · Footage", "#3f789e"), "2": ("2 · Subject matte (BiRefNet)", "#8A8"),
    "3": ("3 · Occupancy — where the subject isn't", "#b06634"), "4": ("4 · Reframe 16:9 → 9:16 (follows the head)", "#a1309b"),
    "5": ("5 · Planar track — text stays on the wall", "#88A"), "6": ("6 · Music: beat grid + lyric-aligned words", "#b58b2a"),
}

NOTE = """# Typeset — where can words live in this shot?

**Typeset** puts lyrics and captions *inside* real footage: behind the person, on the wall, following the head, reframed for vertical. This graph runs every analysis the Typeset editor uses, on one clip and one song, all local and deterministic:

1. **Footage** → frames + fps (`typeset_walk_night.mp4` in your input folder).
2. **BiRefNet** cuts out the subject (MASK).
3. **Occupancy Grid** — per frame, how much of each cell the subject covers. Typeset places `behind` text where it stays readable. Red = subject, green = free.
4. **Mask → Tracks → Reframe Crop** — a dead-zone, critically damped virtual camera that follows the head; the saved video is the 9:16 crop.
5. **Planar Track** — a quad drawn on the roller shutter at frame 70 is tracked forwards and backwards with homographies while the person walks through it (masked out). The JSON is what the renderer uses to warp text onto the wall.
6. **Beat Grid** (beats, downbeats, sections) and **Whisper Words** with lyric alignment (`typeset_neon_rain.flac`): exact lyric spelling, sung timing.

Nodes: `typeset_nodes` (MIT). Every JSON output matches docs/SCHEMA.md and feeds the Typeset renderer directly."""


def ui_workflow(info: dict) -> dict:
    nodes, links = [], []
    link_id = 0
    out_links: dict[tuple[int, int], list[int]] = {}
    incoming: dict[int, dict[str, int]] = {}
    for nid, (cls, inputs, *_r) in SHOW.items():
        for name, v in inputs.items():
            if isinstance(v, tuple) and v[0] == "link":
                link_id += 1
                src, slot = v[1], v[2]
                stype = info[SHOW[src][0]]["output"][slot]
                links.append([link_id, src, slot, nid, None, stype])  # to_slot filled below
                out_links.setdefault((src, slot), []).append(link_id)
                incoming.setdefault(nid, {})[name] = link_id
    link_by_id = {l[0]: l for l in links}
    order = 0
    for nid, (cls, inputs, _pos, _size, group) in SHOW.items():
        pos, size = LAYOUT[nid][:2], LAYOUT[nid][2:]
        spec = info[cls]
        req, opt = spec["input"].get("required", {}), spec["input"].get("optional", {})
        order_names = spec.get("input_order", {})
        names = list(order_names.get("required", req.keys())) + list(order_names.get("optional", opt.keys()))
        allspec = {**req, **opt}
        ui_inputs, widgets = [], []
        for name in names:
            t = allspec[name][0]
            meta = allspec[name][1] if len(allspec[name]) > 1 else {}
            is_widget = (isinstance(t, list) or t in ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO")) and not meta.get("forceInput")
            linked = incoming.get(nid, {}).get(name)
            if is_widget:
                default = meta.get("default", (t[0] if isinstance(t, list) and t else None))
                val = inputs.get(name, default)
                widgets.append(None if isinstance(val, tuple) else val)
                if meta.get("control_after_generate"):
                    widgets.append("fixed")
                if t == "COMBO" and (meta.get("video_upload") or meta.get("audio_upload") or meta.get("image_upload")):
                    widgets.append(None)  # the upload button widget
            if linked or not is_widget:
                entry = {"name": name, "type": "COMBO" if isinstance(t, list) else t, "link": linked}
                if is_widget:
                    entry["widget"] = {"name": name}
                if linked:
                    link_by_id[linked][4] = len(ui_inputs)
                ui_inputs.append(entry)
        outputs = [{"name": n, "type": t, "links": out_links.get((nid, i), []), "slot_index": i}
                   for i, (n, t) in enumerate(zip(spec.get("output_name", spec["output"]), spec["output"]))]
        if cls == "VHS_VideoCombine":  # VHS stores its (format-dependent) widgets as an object
            widgets = {k: v for k, v in inputs.items() if not isinstance(v, tuple)}
            widgets["videopreview"] = {"hidden": False, "paused": False, "params": {}}
        nodes.append({"id": nid, "type": cls, "pos": list(pos), "size": list(size), "flags": {}, "order": order, "mode": 0,
                      "inputs": ui_inputs, "outputs": outputs, "properties": {"Node name for S&R": cls},
                      "widgets_values": widgets})
        order += 1
    note_id = max(SHOW) + 1
    nodes.append({"id": note_id, "type": "MarkdownNote", "pos": list(NOTE_POS[:2]), "size": list(NOTE_POS[2:]), "flags": {}, "order": order,
                  "mode": 0, "inputs": [], "outputs": [], "properties": {}, "widgets_values": [NOTE],
                  "color": "#432", "bgcolor": "#653"})
    groups = []
    for g, (title, color) in GROUPS.items():
        members = [LAYOUT[k] for k, v in SHOW.items() if v[4] == g]
        x0 = min(m[0] for m in members) - 20; y0 = min(m[1] for m in members) - 70
        x1 = max(m[0] + m[2] for m in members) + 20; y1 = max(m[1] + m[3] for m in members) + 30
        groups.append({"title": title, "bounding": [x0, y0, x1 - x0, y1 - y0], "color": color, "font_size": 24, "flags": {}})
    return {"last_node_id": note_id, "last_link_id": link_id, "nodes": nodes, "links": links, "groups": groups,
            "config": {}, "extra": {"ds": {"scale": 0.45, "offset": [60, 20]}}, "version": 0.4}


def api_workflow() -> dict:
    g = {}
    for nid, (cls, inputs, *_r) in SHOW.items():
        g[str(nid)] = {"class_type": cls, "inputs": {
            k: ([str(v[1]), v[2]] if isinstance(v, tuple) else v) for k, v in inputs.items()}}
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    a = ap.parse_args()
    server_workflows()
    info = httpx.get(f"{a.comfy}/object_info", timeout=60).json()
    missing = sorted({v[0] for v in SHOW.values()} - set(info))
    if missing:
        raise SystemExit(f"ComfyUI lacks nodes: {missing}")
    out = WF / "showcase"
    out.mkdir(exist_ok=True)
    (out / "typeset_analysis.json").write_text(json.dumps(ui_workflow(info), indent=2) + "\n")
    (out / "typeset_analysis.api.json").write_text(json.dumps(api_workflow(), indent=2) + "\n")
    print("wrote server workflows and", out / "typeset_analysis.json")


if __name__ == "__main__":
    main()
