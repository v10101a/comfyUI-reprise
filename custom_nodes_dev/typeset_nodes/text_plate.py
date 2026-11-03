"""Deterministic text plate prototype: readable font rendering before optional LTX motion.

This is deliberately not an image-model edit. Prompt selects neon/chrome styling;
other scene instructions belong to the downstream generative model.
"""
import numpy as np
import torch
from PIL import Image, ImageFilter
from .text_mask import render_text

class TypesetTextPlate:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'image': ('IMAGE',), 'text': ('STRING', {'default': 'NEON'}),
                             'prompt': ('STRING', {'default': 'pink neon lettering'})},
                'optional': {'mask_png': ('STRING', {'default': ''}),
                             'look_json': ('STRING', {'default': '', 'forceInput': True,
                                                      'tooltip': 'From Look (Reprise): sets face, case, colours, card, halo and glow; prompt is then ignored'})}}
    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'run'
    CATEGORY = 'Reprise/text'

    def run(self, image, text, prompt='', mask_png='', look_json=''):
        import json
        h, w = image.shape[1:3]
        if look_json:
            from .looks import resolve_look, draw_look_text
            look = resolve_look(json.loads(look_json))
            if look:
                rows = []
                for frame in image:
                    base = Image.fromarray((frame.detach().cpu().numpy()[..., :3].clip(0,1)*255).astype('uint8')).convert('RGB')
                    out, _ = draw_look_text(base, text, look, size=min(.24, 1.35 / max(len(text), 1)) * (look.get('scale') or 1))
                    rows.append(torch.from_numpy(np.asarray(out).copy()).float()/255)
                return (torch.stack(rows),)
        import folder_paths
        from pathlib import Path
        if mask_png:
            root = Path(folder_paths.get_input_directory()).resolve()
            path = (root / mask_png).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Mask must be inside the ComfyUI input directory')
            mask = Image.open(path).convert('L').resize((w, h))
        else:
            size = min(.24, 1.35 / max(len(text), 1))
            mask = render_text(text, 'Anton', size, .5, .5, w, h)
        style = prompt.lower()
        color = (104, 229, 255) if any(k in style for k in ('blue', 'cyan', 'ice')) else (255, 90, 190)
        if any(k in style for k in ('gold', 'amber', 'yellow')): color = (255, 204, 86)
        chrome = any(k in style for k in ('chrome', 'silver', 'metal'))
        rows = []
        for frame in image:
            base = Image.fromarray((frame.detach().cpu().numpy()[..., :3].clip(0,1)*255).astype('uint8')).convert('RGB')
            if not chrome:
                glow = mask.filter(ImageFilter.GaussianBlur(max(2, h*.018)))
                base = Image.composite(Image.new('RGB', (w,h), color), base, glow)
                ink = Image.new('RGB', (w,h), tuple(min(255, int(c*.35+165)) for c in color))
            else:
                yy=np.arange(h)[:,None,None]
                value=(160+80*np.sin(yy/max(h,1)*50)).astype('uint8')
                ink=Image.fromarray(np.tile(value,(1,w,3)), 'RGB')
            base=Image.composite(ink,base,mask)
            rows.append(torch.from_numpy(np.asarray(base).copy()).float()/255)
        return (torch.stack(rows),)

NODE_CLASS_MAPPINGS = {'TypesetTextPlate': TypesetTextPlate}
NODE_DISPLAY_NAME_MAPPINGS = {'TypesetTextPlate': 'Text Plate • deterministic prototype (Reprise)'}
