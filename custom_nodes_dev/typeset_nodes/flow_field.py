"""TypesetFlowField: footage → motion field that pushes and smears the type (Typeset "motion" field)."""
import json

import numpy as np

from . import core_vision as cv
from .analysis_nodes import _gray, _img_u8, _preview_indices, _resize_long, _to_tensor


class TypesetFlowField:
    """Dense optical flow (OpenCV DIS, CPU, no model download) between consecutive frames, averaged onto a coarse
    grid. JSON: {fps, cols, rows, scale, frames: [base64 int8 rows×cols×(dx,dy)]}, motion in fractions of the frame
    per frame. The studio integrates it over a short decay so words get pushed by what moves through them."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001}),
        }, "optional": {
            "long_side_cells": ("INT", {"default": cv.FLOW_LONG, "min": 8, "max": 256}),
            "preview_frames": ("INT", {"default": 8, "min": 0, "max": 100000, "tooltip": "0 = no preview; ≥ frames = all frames"}),
        }}

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("flow_json", "preview")
    FUNCTION = "run"
    CATEGORY = "typeset/analysis"

    def run(self, images, fps, long_side_cells=cv.FLOW_LONG, preview_frames=8):
        B, H, W = images.shape[:3]
        cols, rows = cv.flow_dims(W, H, long_side_cells)
        grids = cv.flow_grids([_gray(images, i) for i in range(B)], cols, rows)
        doc = cv.flow_doc(grids, float(fps))
        prev = []
        for i in _preview_indices(B, preview_frames):
            img = _img_u8(images, i)
            vis = cv.flow_preview(grids[i], doc["scale"], (W, H))
            prev.append(_resize_long((img.astype(np.float32) * .35 + vis.astype(np.float32) * .65).astype(np.uint8), 768))
        import torch
        return (json.dumps(doc), _to_tensor(prev) if prev else torch.zeros(1, 64, 64, 3))


NODE_CLASS_MAPPINGS = {"TypesetFlowField": TypesetFlowField}
NODE_DISPLAY_NAME_MAPPINGS = {"TypesetFlowField": "Motion Field • optical flow (typeset)"}
