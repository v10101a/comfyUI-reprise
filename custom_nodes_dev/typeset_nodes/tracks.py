"""MaskToTracks — per-frame bbox of the largest connected blob in a MASK batch -> tracks.json (SCHEMA §2).

Input: a MASK batch [B, H, W] (0..1) or an IMAGE batch of mattes [B, H, W, C] (alpha channel if C == 4,
else luminance). Output: tracks.json string:

    {"fps": 24, "frames": B,
     "tracks": [{"id": "person0", "label": "person",
                 "frames": [{"f": 0, "bbox": [x, y, w, h], "cx": .., "cy": ..}, ...]}]}

bbox is normalized [x, y, w, h] and is the *raw* bbox of the largest connected component of
(mask > threshold). Frames whose mask area is below `min_area` (fraction of the frame; default 0.2 %)
are omitted — the renderer treats missing frames as "not visible". For label "person" the anchor
(cx, cy) sits in the top ~20 % of the bbox (head area), horizontally centered; for other labels it is
the bbox center. `smooth` applies a centered moving average to cx/cy only (bbox stays honest).
"""
import json

import cv2
import numpy as np
import torch

try:
    from . import core_vision as cv
except ImportError:  # loaded as a standalone file (tests, scripts)
    import importlib.util as _ilu
    import sys as _sys
    from pathlib import Path as _Path
    cv = _sys.modules.get("typeset_core_vision")
    if cv is None:
        _spec = _ilu.spec_from_file_location("typeset_core_vision", _Path(__file__).with_name("core_vision.py"))
        cv = _ilu.module_from_spec(_spec)
        _sys.modules["typeset_core_vision"] = cv
        _spec.loader.exec_module(cv)


def _largest_component(binary: np.ndarray):
    """Return (x, y, w, h, area) in pixels for the largest 8-connected blob of a uint8 mask, or None."""
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n <= 1:
        return None
    # row 0 is the background
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = (int(v) for v in stats[idx])
    return x, y, w, h, area


class MaskToTracks:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001}),
                "label": ("STRING", {"default": "person"}),
            },
            "optional": {
                "mask": ("MASK",),
                "images": ("IMAGE", {"tooltip": "Alternative input: RGBA mattes (alpha used) or grayscale mattes."}),
                "track_id": ("STRING", {"default": "person0"}),
                "threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "min_area": ("FLOAT", {"default": 0.002, "min": 0.0, "max": 1.0, "step": 0.0005,
                                       "tooltip": "Frames whose blob covers less than this fraction of the frame are omitted."}),
                "smooth": ("INT", {"default": 3, "min": 0, "max": 15, "step": 1,
                                   "tooltip": "Moving-average window (frames) applied to cx/cy only. 0/1 = off."}),
                "max_side": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 32,
                                     "tooltip": "Masks are downscaled to this long side before blob analysis (speed)."}),
                "frame_offset": ("INT", {"default": 0, "min": 0, "max": 10000000,
                                         "tooltip": "Index of this batch's first frame in the clip (chunked processing)."}),
                "raw": ("BOOLEAN", {"default": False, "tooltip":
                        "Skip smoothing/rounding of cx/cy so chunks can be merged later (core_vision.merge_track_chunks)."}),
            },
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("tracks_json", "visible_frames")
    FUNCTION = "run"
    CATEGORY = "typeset/analysis"

    def run(self, fps, label, mask=None, images=None, track_id="person0", threshold=0.5,
            min_area=0.002, smooth=3, max_side=512, frame_offset=0, raw=False):
        if mask is None and images is None:
            raise ValueError("MaskToTracks needs a `mask` or `images` input")
        if mask is None:
            img = images
            if img.ndim == 4 and img.shape[-1] == 4:
                mask = img[..., 3]
            elif img.ndim == 4:
                mask = img[..., :3].mean(dim=-1)
            else:
                mask = img
        if mask.ndim == 2:
            mask = mask.unsqueeze(0)
        mask = mask.detach().cpu()
        B, H, W = mask.shape

        scale = min(1.0, float(max_side) / float(max(H, W)))
        frames = []
        for f in range(B):
            m = mask[f]
            if scale < 1.0:
                m = torch.nn.functional.interpolate(m[None, None], scale_factor=scale, mode="area")[0, 0]
            binary = (m.numpy() > threshold).astype(np.uint8)
            h, w = binary.shape
            comp = _largest_component(binary)
            if comp is None:
                continue
            x, y, bw, bh, area = comp
            if area / float(h * w) < min_area:
                continue
            nx, ny, nw, nh = x / w, y / h, bw / w, bh / h
            cx = nx + nw / 2.0
            cy = ny + nh * 0.10 if label.lower() == "person" else ny + nh / 2.0
            frames.append({"f": f + int(frame_offset), "bbox": [round(nx, 4), round(ny, 4), round(nw, 4), round(nh, 4)],
                           "cx": cx, "cy": cy})

        if not raw:
            frames = cv.smooth_track_frames(frames, smooth)
        out = {
            "fps": float(fps),
            "frames": int(B),
            "tracks": [{"id": track_id, "label": label, "frames": frames}],
        }
        return (json.dumps(out), len(frames))


NODE_CLASS_MAPPINGS = {"MaskToTracks": MaskToTracks}
NODE_DISPLAY_NAME_MAPPINGS = {"MaskToTracks": "Mask → Tracks JSON (typeset)"}
