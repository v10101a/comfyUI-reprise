"""Shim: the CV logic lives in the ComfyUI node pack (custom_nodes_dev/typeset_nodes/core_vision.py) so the
nodes and the server's in-process fallback run the exact same code. Loaded by path to avoid importing the
pack's ComfyUI/torch-dependent __init__."""
import importlib.util as _ilu
import os as _os
import sys as _sys
from pathlib import Path as _Path

_PATH = _Path(_os.environ.get("TYPESET_NODES_DIR", _Path(__file__).resolve().parents[2] / "custom_nodes_dev" / "typeset_nodes")) / "core_vision.py"
if "typeset_core_vision" not in _sys.modules:
    _spec = _ilu.spec_from_file_location("typeset_core_vision", _PATH)
    _mod = _ilu.module_from_spec(_spec)
    _sys.modules["typeset_core_vision"] = _mod
    _spec.loader.exec_module(_mod)
from typeset_core_vision import *  # noqa: E402,F401,F403
from typeset_core_vision import (_quad_mask, _sane_quad, _subject_free, alignment_score, smooth_corners, compute_crop, surface_track_doc, merge_track_chunks,  # noqa: E402,F401
                                 occupancy_doc, OCC_LONG)
