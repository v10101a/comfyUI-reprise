"""TypesetMatteRefine: make a subject matte safe to put words behind.

Segmenters drop parts of a person that look like the background: a white t-shirt against a bright wall becomes a
hole, and words behind the subject then show straight through their chest. This node fills background regions that
are fully enclosed by the subject (not connected to the frame edge) up to `max_hole` of the subject's area, so real
gaps (between the legs, an arm away from the body) stay open while holes inside the body close. It also removes
specks, and returns the footage as RGBA with the refined alpha, ready for SaveImage.
"""
import cv2
import numpy as np
import torch


def fill_holes(alpha: np.ndarray, max_hole: float = 0.25, min_speck: float = 0.002, feather: float = 1.5) -> np.ndarray:
    """alpha: HxW float 0..1 -> refined alpha. Holes = background components not touching the border, each at most
    max_hole × subject area; specks = foreground components smaller than min_speck × frame area."""
    h, w = alpha.shape
    fg = (alpha > .5).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < min_speck * h * w:
            fg[lab == i] = 0
    alpha = alpha * fg if n > 1 else alpha
    subject = int(fg.sum())
    if subject == 0:
        return alpha
    bg = (1 - fg).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bg, connectivity=4)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])).tolist())
    holes = np.zeros((h, w), np.float32)
    for i in range(1, n):
        if i not in border and stats[i, cv2.CC_STAT_AREA] <= max_hole * subject:
            holes[lab == i] = 1.0
    if holes.any():
        if feather > 0:
            holes = np.maximum(holes, cv2.GaussianBlur(holes, (0, 0), feather) * (cv2.dilate(holes, np.ones((3, 3), np.uint8)) > 0))
        alpha = np.maximum(alpha, holes)
    return alpha


class TypesetMatteRefine:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "mask": ("MASK",),
        }, "optional": {
            "max_hole": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01,
                                   "tooltip": "Fill enclosed holes up to this fraction of the subject's area (0 = off)."}),
            "min_speck": ("FLOAT", {"default": 0.002, "min": 0.0, "max": 0.05, "step": 0.001,
                                    "tooltip": "Drop foreground blobs smaller than this fraction of the frame."}),
        }}

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("rgba", "mask")
    FUNCTION = "run"
    CATEGORY = "Reprise/analysis"
    DESCRIPTION = "Close holes inside the subject (white shirt vs bright wall) so words behind them stay behind them."

    def run(self, images, mask, max_hole=0.25, min_speck=0.002):
        B = images.shape[0]
        H, W = images.shape[1:3]
        out = []
        for i in range(B):
            m = mask[min(i, mask.shape[0] - 1)].cpu().numpy().astype(np.float32)
            if m.shape != (H, W):
                m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)
            out.append(fill_holes(m, max_hole, min_speck) if max_hole > 0 or min_speck > 0 else m)
        alpha = torch.from_numpy(np.stack(out))
        rgba = torch.cat([images[..., :3].cpu(), alpha[..., None]], dim=-1)
        return (rgba, alpha)


NODE_CLASS_MAPPINGS = {"TypesetMatteRefine": TypesetMatteRefine}
NODE_DISPLAY_NAME_MAPPINGS = {"TypesetMatteRefine": "Matte Refine • fill holes in the subject (Reprise)"}
