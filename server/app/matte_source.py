"""Resolve the exact take a matte job consumes, independently of editor selection."""
from __future__ import annotations

import math


def matte_source(project, layer_id: str | None = None) -> dict:
    if layer_id is None:
        video = project.media.video
        if not video:
            raise ValueError("Choose a visual layer or upload footage before extracting a subject")
        return dict(layerId=None, assetId=None, path=video.path, kind="video", **{"in": 0},
                    out=project.duration, width=project.width, height=project.height, fps=project.fps)
    layer = next((l for l in getattr(project, "layers", None) or []
                  if isinstance(l, dict) and l.get("id") == layer_id), None)
    if not layer or layer.get("kind") != "media":
        raise ValueError("Choose an existing image or video layer for the subject matte")
    asset = next((a for a in getattr(project, "assets", None) or []
                  if isinstance(a, dict) and a.get("id") == layer.get("assetId")), None)
    if not asset or asset.get("kind") not in ("image", "video") or not asset.get("path"):
        raise ValueError("The selected layer has no usable image or video asset")
    start, end = float(layer.get("in", 0)), float(layer.get("out", 0))
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError("The selected layer needs a valid source in/out range")
    if asset["kind"] == "video" and start >= float(asset.get("duration") or 0):
        raise ValueError("The selected layer starts past the end of its video")
    w, h = int(asset.get("width") or 0), int(asset.get("height") or 0)
    if w <= 0 or h <= 0:
        raise ValueError("The selected asset has no image dimensions")
    # Native aspect, without cover-cropping: the editor may move, rotate or shrink the layer later.
    scale = min(1, 4096 / max(w, h))
    return dict(layerId=layer_id, assetId=asset["id"], path=asset["path"], kind=asset["kind"],
                **{"in": start}, out=end, width=max(2, round(w * scale / 2) * 2),
                height=max(2, round(h * scale / 2) * 2), fps=project.fps)


def check_matte_source(project, source: dict):
    if matte_source(project, source["layerId"]) != source:
        raise ValueError("Matte source changed during extraction; run the matte again for the current take")
