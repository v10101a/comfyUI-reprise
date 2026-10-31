"""SaveTextFile — write a STRING to the ComfyUI output dir and expose it as a downloadable job output.

Why not core `SaveText`? Its `ui` payload is {"text": (str,), "files": [SavedResult]}: comfy-api-proxy
turns `files` into an output of type "file" and ignores the bare string. Our server-side contract
(docs/SCHEMA.md §3) wants the sidecar output type "text", and comfy-api-proxy maps the history key
`text` -> kind "text" *only* for list items that are dicts carrying `filename` (+ `subfolder`, `type`).
So this node returns exactly that shape:

    {"ui": {"text": [{"filename": "words_00001_.json", "subfolder": "typeset/<id>", "type": "output"}]},
     "result": (text,)}

which the SDK then exposes as `Output(type="text", name="words_00001_.json")` on this node id.
"""
import json
import os

import folder_paths


class SaveTextFile:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
                "filename_prefix": ("STRING", {"default": "typeset/text"}),
                "extension": (["json", "txt"], {"default": "json"}),
            },
            "optional": {
                "pretty_json": ("BOOLEAN", {"default": True,
                                            "tooltip": "Re-indent valid JSON before writing (ignored for txt)."}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "typeset/io"
    DESCRIPTION = "Writes the string to <output>/<filename_prefix>_NNNNN_.<ext> and lists it as a text output."

    def save(self, text, filename_prefix, extension="json", pretty_json=True):
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), 1, 1
        )
        os.makedirs(full_output_folder, exist_ok=True)
        # Same naming convention as SaveImage: <prefix>_00001_.<ext>  (counter increments per run).
        file = f"{filename}_{counter:05}_.{extension}"
        path = os.path.join(full_output_folder, file)

        payload = text
        if extension == "json" and pretty_json:
            try:
                payload = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(payload)

        return {
            "ui": {"text": [{"filename": file, "subfolder": subfolder, "type": "output"}]},
            "result": (text,),
        }


NODE_CLASS_MAPPINGS = {"SaveTextFile": SaveTextFile}
NODE_DISPLAY_NAME_MAPPINGS = {"SaveTextFile": "Save Text File (typeset)"}
