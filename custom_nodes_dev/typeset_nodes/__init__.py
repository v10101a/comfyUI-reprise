"""Typeset nodes — ComfyUI node pack for the Typeset lyric / kinetic-typography engine.

Nodes (all V1 node API):
  TypesetOccupancyGrid      MASK batch -> occupancy grid JSON + heatmap preview (where text stays readable)
  TypesetPlanarTrack        IMAGE batch + quad (+ subject MASK) -> per-frame corners JSON + preview
  TypesetReframeCrop        tracks JSON / MASK + aspect -> smoothed crop JSON + cropped preview
  TypesetBeatGrid           AUDIO -> beats / downbeats / sections JSON + waveform preview
  TypesetLoadImageSequence  folder of (RGBA) PNGs -> IMAGE + MASK batch
  AudioBeatMarkers  AUDIO -> beat times JSON (librosa)
  WhisperWords      AUDIO (+ optional lyrics) -> words.json STRING (faster-whisper, CPU int8)
  TypesetAlignLyrics AUDIO + known lyrics -> words.json by forced alignment (HDemucs vocals, MMS_FA CTC, onsets) + preview
  SaveTextFile      STRING -> .json/.txt in the output dir, exposed as a downloadable "text" output
  MaskToTracks      MASK / matte IMAGE batch -> tracks.json STRING (largest blob bbox per frame)
  TextToMask        text + bundled OFL font -> MASK + IMAGE (white text on black)

Each node lives in its own module; this file only aggregates the mappings.
"""
from .beats import NODE_CLASS_MAPPINGS as _beats, NODE_DISPLAY_NAME_MAPPINGS as _beats_names
from .save_text import NODE_CLASS_MAPPINGS as _save, NODE_DISPLAY_NAME_MAPPINGS as _save_names
from .tracks import NODE_CLASS_MAPPINGS as _tracks, NODE_DISPLAY_NAME_MAPPINGS as _tracks_names
from .text_mask import NODE_CLASS_MAPPINGS as _text, NODE_DISPLAY_NAME_MAPPINGS as _text_names
from .whisper_words import NODE_CLASS_MAPPINGS as _whisper, NODE_DISPLAY_NAME_MAPPINGS as _whisper_names

from .text_plate import NODE_CLASS_MAPPINGS as _plate, NODE_DISPLAY_NAME_MAPPINGS as _plate_names
from .analysis_nodes import NODE_CLASS_MAPPINGS as _analysis, NODE_DISPLAY_NAME_MAPPINGS as _analysis_names
from .lyric_align import NODE_CLASS_MAPPINGS as _align, NODE_DISPLAY_NAME_MAPPINGS as _align_names

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
for _m, _n in ((_beats, _beats_names), (_save, _save_names), (_tracks, _tracks_names),
               (_text, _text_names), (_whisper, _whisper_names), (_plate, _plate_names),
               (_analysis, _analysis_names), (_align, _align_names)):
    NODE_CLASS_MAPPINGS.update(_m)
    NODE_DISPLAY_NAME_MAPPINGS.update(_n)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
