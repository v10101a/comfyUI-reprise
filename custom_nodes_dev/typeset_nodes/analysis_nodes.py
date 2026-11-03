"""Reprise analysis nodes: where can words live in this shot?

  TypesetLoadImageSequence  folder of PNGs (e.g. RGBA mattes) → IMAGE + MASK (alpha) batch
  TypesetOccupancyGrid      MASK batch → occupancy grid JSON (+ heatmap preview)
  TypesetPlanarTrack        IMAGE batch + quad + key frame (+ subject MASK) → per-frame corners JSON (+ preview)
  TypesetReframeCrop        tracks JSON or MASK batch + aspect → smoothed crop JSON (+ cropped preview)

All math is in core_vision.py (shared with the Reprise server); these classes only convert ComfyUI
tensors ([B,H,W,C] float 0..1 IMAGE, [B,H,W] float MASK) to numpy and draw previews.
"""
import glob
import json
import os

import cv2
import numpy as np
import torch

from . import core_vision as cv

ASPECTS = list(cv.ASPECTS.keys())


# ---- tensor helpers ----------------------------------------------------------------------

def _mask_u8(mask: torch.Tensor, i: int) -> np.ndarray:
    return (mask[i].detach().cpu().float().clamp(0, 1).numpy() * 255.0 + 0.5).astype(np.uint8)


def _img_u8(images: torch.Tensor, i: int) -> np.ndarray:
    return (images[i, ..., :3].detach().cpu().float().clamp(0, 1).numpy() * 255.0 + 0.5).astype(np.uint8)


def _gray(images: torch.Tensor, i: int) -> np.ndarray:
    return cv2.cvtColor(_img_u8(images, i), cv2.COLOR_RGB2GRAY)


def _to_tensor(frames: list[np.ndarray]) -> torch.Tensor:
    return torch.from_numpy(np.stack(frames).astype(np.float32) / 255.0)


def _preview_indices(n: int, count: int) -> list[int]:
    if count <= 0 or n == 0:
        return []
    if count >= n:
        return list(range(n))
    return sorted({int(round(i * (n - 1) / (count - 1))) for i in range(count)}) if count > 1 else [n // 2]


def _resize_long(img: np.ndarray, long_side: int) -> np.ndarray:
    h, w = img.shape[:2]
    s = long_side / max(h, w)
    return cv2.resize(img, (max(2, int(w * s)), max(2, int(h * s))), interpolation=cv2.INTER_AREA) if s < 1 else img


def _label(img: np.ndarray, text: str) -> np.ndarray:
    cv2.putText(img, text, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(img, text, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    return img


# ---- loader ------------------------------------------------------------------------------

class TypesetLoadImageSequence:
    """Loads `<input dir>/<directory>/<pattern>` sorted by name. MASK = alpha channel (or luminance when the
    PNGs have no alpha). An empty `directory` returns a single empty 64×64 frame = "no subject"."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "directory": ("STRING", {"default": "typeset/matte", "tooltip": "Folder relative to ComfyUI's input dir (or absolute)."}),
            "pattern": ("STRING", {"default": "*.png"}),
        }, "optional": {
            "max_frames": ("INT", {"default": 0, "min": 0, "max": 100000, "tooltip": "0 = all"}),
        }}

    RETURN_TYPES = ("IMAGE", "MASK", "INT")
    RETURN_NAMES = ("images", "mask", "count")
    FUNCTION = "load"
    CATEGORY = "Reprise/io"

    @classmethod
    def IS_CHANGED(cls, directory, pattern, max_frames=0):
        files = cls._files(directory, pattern, max_frames)
        return ";".join(f"{f}:{os.path.getmtime(f)}" for f in files)

    @staticmethod
    def _files(directory, pattern, max_frames=0):
        if not directory.strip():
            return []
        root = directory
        if not os.path.isabs(root):
            import folder_paths
            root = os.path.join(folder_paths.get_input_directory(), directory)
        files = sorted(glob.glob(os.path.join(root, pattern)))
        return files[:max_frames] if max_frames else files

    def load(self, directory, pattern, max_frames=0):
        from PIL import Image
        files = self._files(directory, pattern, max_frames)
        if not files:
            if directory.strip():
                raise FileNotFoundError(f"No files match {pattern} in {directory}")
            return (torch.zeros(1, 64, 64, 3), torch.zeros(1, 64, 64), 0)
        imgs, masks = [], []
        for f in files:
            with Image.open(f) as im:
                if im.mode in ("RGBA", "LA") or "transparency" in im.info:
                    rgba = np.asarray(im.convert("RGBA"))
                    imgs.append(rgba[..., :3]); masks.append(rgba[..., 3])
                else:
                    rgb = np.asarray(im.convert("RGB"))
                    imgs.append(rgb); masks.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
        return (_to_tensor(imgs), _to_tensor(masks), len(files))


# ---- occupancy ---------------------------------------------------------------------------

def occupancy_heatmap(cells: np.ndarray, frame: np.ndarray | None, size: tuple[int, int]) -> np.ndarray:
    """Red = subject, green = free; drawn over the frame when given. size = (w, h)."""
    w, h = size
    heat = cv2.resize(cells, (w, h), interpolation=cv2.INTER_NEAREST).astype(np.float32) / 255.0
    color = np.stack([heat, 1 - heat, np.zeros_like(heat)], -1) * 255  # RGB
    base = frame.astype(np.float32) if frame is not None else np.full((h, w, 3), 40, np.float32)
    out = (base * 0.55 + color * 0.45).astype(np.uint8)
    rows, cols = cells.shape
    for c in range(1, cols):
        x = int(c * w / cols); out[:, x] = (out[:, x] * 0.6).astype(np.uint8)
    for r in range(1, rows):
        y = int(r * h / rows); out[y, :] = (out[y, :] * 0.6).astype(np.uint8)
    return out


class TypesetOccupancyGrid:
    """How much of each grid cell the subject covers, per frame — the input for placing text where it stays
    readable. JSON: {fps, cols, rows, step, frames: [base64(cols*rows uint8, row-major, 0..255)]}."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "mask": ("MASK", {"tooltip": "Subject matte batch (1 = subject)."}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001}),
            "long_side_cells": ("INT", {"default": cv.OCC_LONG, "min": 4, "max": 128}),
        }, "optional": {
            "images": ("IMAGE", {"tooltip": "Optional frames to draw the heatmap over."}),
            "preview_frames": ("INT", {"default": 6, "min": 0, "max": 64}),
        }}

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("occupancy_json", "preview")
    FUNCTION = "run"
    CATEGORY = "Reprise/analysis"

    def run(self, mask, fps, long_side_cells=cv.OCC_LONG, images=None, preview_frames=6):
        if mask.ndim == 2:
            mask = mask.unsqueeze(0)
        B, H, W = mask.shape
        alphas = [_mask_u8(mask, i) for i in range(B)]
        doc = cv.occupancy_doc(alphas, W, H, float(fps), long_side_cells)
        prev = []
        pw, ph = (640, max(2, int(640 * H / W))) if W >= H else (max(2, int(640 * W / H)), 640)
        for i in _preview_indices(B, preview_frames):
            cells = cv.decode_occupancy(doc["frames"][i], doc["cols"], doc["rows"])
            frame = cv2.resize(_img_u8(images, min(i, images.shape[0] - 1)), (pw, ph)) if images is not None else None
            prev.append(_label(occupancy_heatmap(cells, frame, (pw, ph)), f"f{i}"))
        return (json.dumps(doc), _to_tensor(prev) if prev else torch.zeros(1, 64, 64, 3))


# ---- planar track -----------------------------------------------------------------------

def draw_quad(img: np.ndarray, corners_px: np.ndarray, conf: float | None, f: int) -> np.ndarray:
    img = img.copy()
    if corners_px is not None:
        q = np.round(corners_px).astype(np.int32)
        H = cv2.getPerspectiveTransform(np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), np.float32(corners_px))
        for t in np.linspace(0.2, 0.8, 4):
            a = cv2.perspectiveTransform(np.float32([[[t, 0]], [[t, 1]], [[0, t]], [[1, t]]]), H).reshape(-1, 2)
            cv2.line(img, tuple(int(v) for v in a[0]), tuple(int(v) for v in a[1]), (255, 200, 0), 2, cv2.LINE_AA)
            cv2.line(img, tuple(int(v) for v in a[2]), tuple(int(v) for v in a[3]), (255, 200, 0), 2, cv2.LINE_AA)
        cv2.polylines(img, [q], True, (0, 255, 0), 3, cv2.LINE_AA)
    return _label(img, f"f{f} " + (f"conf {conf:.2f}" if conf is not None else "lost"))


class TypesetPlanarTrack:
    """Glue a quad to a wall: features inside (and around) the key-frame quad, subject masked out, LK tracked
    forwards and backwards, key→frame homography with RANSAC; then every frame is re-aligned directly to the key
    frame (masked high-pass ECC + coarse template search) and the simplest of translation / similarity /
    homography that the alignment supports is kept (blank walls stay rigid instead of skewing); shape sanity vs
    the key frame, confidence = alignment, temporal smoothing; low-confidence frames dropped.
    JSON: {fps, frames: [{f, corners: [[x,y]×4 normalized TL,TR,BR,BL], conf}]}."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "corners": ("STRING", {"default": "[[0.36,0.03],[0.50,0.08],[0.50,0.62],[0.36,0.68]]",
                                   "tooltip": "Normalized [[x,y]×4] at key_frame, order TL, TR, BR, BL."}),
            "key_frame": ("INT", {"default": 0, "min": 0, "max": 100000}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001}),
        }, "optional": {
            "subject_mask": ("MASK", {"tooltip": "Matte of moving foreground (people) to ignore."}),
            "feature_region": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.05,
                                         "tooltip": "Also use features in the quad grown by this fraction (same plane)."}),
            "min_confidence": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
            "smooth": ("INT", {"default": 2, "min": 0, "max": 10}),
            "preview_frames": ("INT", {"default": 8, "min": 0, "max": 100000, "tooltip": "0 = no preview; ≥ frames = all frames"}),
        }}

    RETURN_TYPES = ("STRING", "IMAGE", "INT")
    RETURN_NAMES = ("surface_json", "preview", "tracked_frames")
    FUNCTION = "run"
    CATEGORY = "Reprise/analysis"

    def run(self, images, corners, key_frame, fps, subject_mask=None, feature_region=1.0, min_confidence=0.35,
            smooth=2, preview_frames=8):
        B, H, W = images.shape[:3]
        quad = np.asarray(json.loads(corners) if isinstance(corners, str) else corners, float).reshape(4, 2) * [W, H]
        key = int(min(max(0, key_frame), B - 1))
        grays: dict[int, np.ndarray] = {}

        def frame(i):
            if i not in grays:
                grays[i] = _gray(images, i)
            return grays[i]

        def subject(i):
            if subject_mask is None or i >= subject_mask.shape[0]:
                return None
            m = _mask_u8(subject_mask, i)
            return m if m.shape == (H, W) else cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)

        params = cv.TrackParams(expand=feature_region, min_conf=min_confidence, smooth=smooth)
        track = cv.track_plane(frame, B, key, quad, subject, params)
        doc = cv.surface_track_doc(track, W, H, float(fps))
        prev = []
        for i in _preview_indices(B, preview_frames):
            c, conf = track.get(i, (None, None))
            prev.append(_resize_long(draw_quad(_img_u8(images, i), c, conf, i), 768))
        return (json.dumps(doc), _to_tensor(prev) if prev else torch.zeros(1, 64, 64, 3), len(track))


# ---- reframe ----------------------------------------------------------------------------

class TypesetReframeCrop:
    """Landscape → vertical (or any aspect) virtual camera that follows the subject: dead zone, look-ahead,
    critically damped spring, clamped inside the frame, keeps tracked surfaces in view when possible.
    JSON: {fps, aspect, frames: [{f, x, y, w, h}]} in source-normalized coordinates."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "aspect": (ASPECTS, {"default": "9:16"}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001}),
        }, "optional": {
            "tracks_json": ("STRING", {"forceInput": True, "tooltip": "tracks.json (e.g. from Mask → Tracks)."}),
            "mask": ("MASK", {"tooltip": "Used to derive a person track when tracks_json is not connected."}),
            "images": ("IMAGE", {"tooltip": "Source frames: sets the size and is cropped for the preview."}),
            "surfaces_json": ("STRING", {"default": "", "tooltip": "Optional surface track JSON (one doc, or a list/dict of docs)."}),
            "width": ("INT", {"default": 0, "min": 0, "max": 16384, "tooltip": "Source width when no images/mask are connected."}),
            "height": ("INT", {"default": 0, "min": 0, "max": 16384}),
            "frames": ("INT", {"default": 0, "min": 0, "max": 1000000, "tooltip": "Frame count when no images/mask are connected."}),
            "track_id": ("STRING", {"default": "person0"}),
            "focus_json": ("STRING", {"default": "", "multiline": True, "tooltip":
                "Regions the crop must contain, e.g. a generated word: [{\"start\": 13.93, \"end\": 16.32, "
                "\"box\": [x0, y0, x1, y1], \"mode\": \"auto\"|\"pan\"}] (seconds, source-normalized). "
                "auto = follow but keep the box in frame, zoom out (letterbox) if it is too big; pan = scan across it."}),
        }}

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("crop_json", "cropped_preview")
    FUNCTION = "run"
    CATEGORY = "Reprise/analysis"

    def run(self, aspect, fps, tracks_json=None, mask=None, images=None, surfaces_json="", width=0, height=0,
            frames=0, track_id="person0", focus_json=""):
        src = images if images is not None else mask
        if src is not None:
            n, H, W = src.shape[0], src.shape[1], src.shape[2]
        else:
            n, H, W = frames, height, width
        if tracks_json:
            tracks = json.loads(tracks_json)
            n = n or int(tracks.get("frames", 0))
        elif mask is not None:
            from .tracks import MaskToTracks
            tracks = json.loads(MaskToTracks().run(fps, "person", mask=mask, track_id=track_id)[0])
        else:
            tracks = None
        if not (n and W and H):
            raise ValueError("Connect images or mask, or set width/height/frames")
        surfaces = None
        if surfaces_json and surfaces_json.strip():
            s = json.loads(surfaces_json)
            surfaces = [s] if isinstance(s, dict) and "frames" in s else s
        focus = json.loads(focus_json) if focus_json and focus_json.strip() else None
        doc = cv.compute_crop(W, H, float(fps), tracks, surfaces, aspect, n, track_id, focus)
        prev = []
        if images is not None:
            ow = int(round(cv.crop_size(W, H, aspect)[0] * W))
            oh = int(round(cv.crop_size(W, H, aspect)[1] * H))
            for fr in doc["frames"]:
                prev.append(cv.render_crop(_img_u8(images, fr["f"]), fr, ow, oh))
        return (json.dumps(doc), _to_tensor(prev) if prev else torch.zeros(1, 64, 64, 3))


NODE_CLASS_MAPPINGS = {
    "TypesetLoadImageSequence": TypesetLoadImageSequence,
    "TypesetOccupancyGrid": TypesetOccupancyGrid,
    "TypesetPlanarTrack": TypesetPlanarTrack,
    "TypesetReframeCrop": TypesetReframeCrop,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "TypesetLoadImageSequence": "Load Image Sequence + Alpha (Reprise)",
    "TypesetOccupancyGrid": "Occupancy Grid — where the subject isn't (Reprise)",
    "TypesetPlanarTrack": "Planar Track — glue a quad to a wall (Reprise)",
    "TypesetReframeCrop": "Reframe Crop — subject-following virtual camera (Reprise)",
}
