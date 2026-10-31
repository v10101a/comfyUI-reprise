"""Typeset nodes — ComfyUI node pack for the Typeset lyric / kinetic-typography engine.

Nodes (all V1 node API):
  TypesetOccupancyGrid      MASK batch -> occupancy grid JSON + heatmap preview (where text stays readable)
  TypesetPlanarTrack        IMAGE batch + quad (+ subject MASK) -> per-frame corners JSON + preview
  TypesetReframeCrop        tracks JSON / MASK + aspect -> smoothed crop JSON + cropped preview
  TypesetBeatGrid           AUDIO -> beats / downbeats / sections JSON + waveform preview
  TypesetLoadImageSequence  folder of (RGBA) PNGs -> IMAGE + MASK batch
  AudioBeatMarkers  AUDIO -> beat times JSON (librosa)
  WhisperWords      AUDIO (+ optional lyrics) -> words.json STRING (faster-whisper, CPU int8)
  TypesetFlowField          IMAGE batch -> motion field JSON (DIS optical flow on a coarse grid) + preview
  TypesetVoiceField         AUDIO -> per-frame vocal loudness / pitch / vibrato / onsets JSON + preview
  TypesetMatteRefine        IMAGE + MASK -> RGBA + MASK with holes inside the subject filled
  TypesetRender             IMAGE + words (+ look, matte, voice/flow fields) -> type burned into the frames
  TypesetAlignLyrics AUDIO + known lyrics -> words.json by forced alignment (HDemucs vocals, MMS_FA CTC, onsets) + preview
  SaveTextFile      STRING -> .json/.txt in the output dir, exposed as a downloadable "text" output
  MaskToTracks      MASK / matte IMAGE batch -> tracks.json STRING (largest blob bbox per frame)
  TextToMask        text + bundled OFL font -> MASK + IMAGE (white text on black)
  TypesetLook       look preset + params -> look_json (= project.look) + type preview
  TypesetGrade      IMAGE batch + grade preset/params (+ beats) -> graded IMAGE + grade_json (= project.grade)

Each node lives in its own module; this file aggregates the mappings and mounts the studio at /typeset.
"""
from .beats import NODE_CLASS_MAPPINGS as _beats, NODE_DISPLAY_NAME_MAPPINGS as _beats_names
from .save_text import NODE_CLASS_MAPPINGS as _save, NODE_DISPLAY_NAME_MAPPINGS as _save_names
from .tracks import NODE_CLASS_MAPPINGS as _tracks, NODE_DISPLAY_NAME_MAPPINGS as _tracks_names
from .text_mask import NODE_CLASS_MAPPINGS as _text, NODE_DISPLAY_NAME_MAPPINGS as _text_names
from .whisper_words import NODE_CLASS_MAPPINGS as _whisper, NODE_DISPLAY_NAME_MAPPINGS as _whisper_names

from .text_plate import NODE_CLASS_MAPPINGS as _plate, NODE_DISPLAY_NAME_MAPPINGS as _plate_names
from .analysis_nodes import NODE_CLASS_MAPPINGS as _analysis, NODE_DISPLAY_NAME_MAPPINGS as _analysis_names
from .lyric_align import NODE_CLASS_MAPPINGS as _align, NODE_DISPLAY_NAME_MAPPINGS as _align_names
from .looks import NODE_CLASS_MAPPINGS as _looks, NODE_DISPLAY_NAME_MAPPINGS as _looks_names
from .flow_field import NODE_CLASS_MAPPINGS as _flow, NODE_DISPLAY_NAME_MAPPINGS as _flow_names
from .voice_field import NODE_CLASS_MAPPINGS as _voice, NODE_DISPLAY_NAME_MAPPINGS as _voice_names
from .render_node import NODE_CLASS_MAPPINGS as _render, NODE_DISPLAY_NAME_MAPPINGS as _render_names
from .matte_refine import NODE_CLASS_MAPPINGS as _refine, NODE_DISPLAY_NAME_MAPPINGS as _refine_names

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
for _m, _n in ((_beats, _beats_names), (_save, _save_names), (_tracks, _tracks_names),
               (_text, _text_names), (_whisper, _whisper_names), (_plate, _plate_names),
               (_analysis, _analysis_names), (_align, _align_names), (_flow, _flow_names), (_voice, _voice_names), (_render, _render_names), (_refine, _refine_names),
               (_looks, _looks_names)):
    NODE_CLASS_MAPPINGS.update(_m)
    NODE_DISPLAY_NAME_MAPPINGS.update(_n)

# The studio opens at http://<comfy>/typeset (see studio_host.py); web/ adds the Typeset sidebar tab.
WEB_DIRECTORY = "./web"
try:
    from server import PromptServer
except ImportError:  # imported outside ComfyUI (tests)
    PromptServer = None
if getattr(PromptServer, "instance", None) is not None:
    from .studio_host import register as _register_studio
    _register_studio(PromptServer.instance)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
