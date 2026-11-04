"""Bring-your-own Comfy workflows: import an API graph, choose what to expose, run it on a project.

A user workflow lives in data/workflows/<id>/ (never the repo's workflows/):
  graph.api.json        the executable API-format graph (from a saved file or Comfy's own graphToPrompt)
  ui.json               the editable UI graph, when it came from inside ComfyUI
  workflow.json         {id, name, candidates, inputs, output, missing, ...}: what the studio shows
  workflow.inputs.json  a regular sidecar (comfy.py) generated from the chosen inputs/output

Running stages the chosen source (an asset, a frame or a time range of the project video) into
ComfyUI's input dir, runs the sidecar with the local runner, and lands the output as a project asset
through service.add_asset (the Layers contract, board cc20), with full provenance in asset.source.
"""
from __future__ import annotations

import json
import copy
import math
import logging
import random
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .comfy import runner, remote_runner
from .config import settings
from .media import ffmpeg, extract_frame
from .store import write_json_atomic

log = logging.getLogger("typeset.workflows")

ROOT_NAME = "workflows"
SIDE = "workflow.inputs.json"
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".m4v", ".gif"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MAX_RANGE = 20.0  # seconds of video sent into a workflow
_registries: dict[str, tuple[float, dict]] = {}
MODEL_FIELDS = {"unet_name", "clip_name", "clip_name1", "clip_name2", "clip_name3", "vae_name",
                "ckpt_name", "lora_name", "control_net_name", "audio_encoder_name", "style_model_name", "gligen_name"}


class WorkflowApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def root() -> Path:
    return settings.data_dir / ROOT_NAME


def _dir(wid: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", wid or ""):
        raise WorkflowApiError(400, "Invalid workflow id")
    d = root() / wid
    if not (d / "workflow.json").is_file():
        raise WorkflowApiError(404, "Workflow not found")
    return d


# ---- registry + graph inspection ------------------------------------------------

def object_info(force: bool = False, *, remote: bool = False) -> dict:
    """Cache each host separately; an unreachable host must never appear ready."""
    run = remote_runner if remote else runner
    if run is None:
        return {}
    url = run.comfyui_url
    cached = _registries.get(url)
    if not force and cached and time.monotonic() - cached[0] < (60 if cached[1] else 5):
        return cached[1]
    try:
        # Comfy Cloud needs its API key on every call and its registry (900+ models) is slow to serve.
        r = httpx.get(f"{url}/object_info", headers=getattr(run, "api_headers", None), timeout=30 if getattr(run, "cloud", False) else 10)
        r.raise_for_status()
        registry = r.json()
    except Exception as exc:
        log.warning("object_info unavailable at %s: %s", url, exc)
        registry = {}
    _registries[url] = (time.monotonic(), registry)
    return registry


def api_graph(data: Any) -> dict | None:
    """Return the API-format graph inside `data`, or None (UI-format workflows have nodes/links)."""
    if isinstance(data, dict):
        for key in ("prompt", "output"):  # {prompt: ...} wrappers from /prompt payloads and graphToPrompt
            if isinstance(data.get(key), dict) and api_graph(data[key]) is not None:
                return data[key]
        nodes = [v for k, v in data.items() if not str(k).startswith("_")]
        if nodes and all(isinstance(v, dict) and "class_type" in v and isinstance(v.get("inputs", {}), dict) for v in nodes):
            return {str(k): v for k, v in data.items() if not str(k).startswith("_")}
    return None


def _title(node: dict, nid: str) -> str:
    return (node.get("_meta") or {}).get("title") or f"{node['class_type']} #{nid}"


def _out_type(cls: str) -> str:
    c = cls.lower()
    return "video" if ("video" in c or "animated" in c or "gif" in c) else "image"


def candidates(graph: dict, registry: dict) -> dict:
    """Every widget value that could be exposed, with a guessed role, plus every output node."""
    ins: list[dict] = []
    outs: list[dict] = []
    for nid, node in graph.items():
        cls = node["class_type"]
        info = registry.get(cls) or {}
        spec_all = {**(info.get("input") or {}).get("required", {}), **(info.get("input") or {}).get("optional", {})}
        for fld, value in (node.get("inputs") or {}).items():
            if isinstance(value, list):  # a link [node, slot], not a widget
                continue
            spec = spec_all.get(fld) or [None]
            typ, opts = spec[0], (spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {})
            role, kind, media = None, None, None
            low = fld.lower()
            if opts.get("image_upload") or (cls.startswith("LoadImage") and low == "image"):
                role, kind, media = "media", "comfy_input_path", "image"
            elif opts.get("video_upload") or ("loadvideo" in cls.lower() and low in ("video", "file")):
                role, kind, media = "media", "comfy_input_path", "video"
            elif opts.get("audio_upload") or (cls == "LoadAudio" and low == "audio"):
                role, kind, media = "media", "comfy_input_path", "audio"  # staged from the song (or an asset's track)
            elif fld in MODEL_FIELDS and isinstance(value, str):
                role, kind = "model", "string"
            elif low in ("seed", "noise_seed") and (typ == "INT" or isinstance(value, int)):
                role, kind = "seed", "int"
            elif typ == "STRING" or (typ is None and isinstance(value, str) and not isinstance(spec[0], list)):
                role, kind = ("prompt" if opts.get("multiline") or low in ("text", "prompt") else "text"), "string"
            elif typ == "INT" or (typ is None and isinstance(value, int) and not isinstance(value, bool)):
                role, kind = "number", "int"
            elif typ == "FLOAT" or (typ is None and isinstance(value, float)):
                role, kind = "number", "float"
            elif typ == "BOOLEAN" or isinstance(value, bool):
                role, kind = "bool", "bool"
            if role is None:
                continue
            c = {"node": nid, "field": fld, "classType": cls, "title": _title(node, nid), "role": role, "kind": kind, "value": value}
            if media:
                c["media"] = media
            for k in ("min", "max", "step"):
                if k in opts:
                    c[k] = opts[k]
            ins.append(c)
        if info.get("output_node") or (not registry and re.match(r"(Save|Preview)", cls)):
            outs.append({"node": nid, "classType": cls, "title": _title(node, nid), "type": _out_type(cls)})
    return {"inputs": ins, "outputs": outs}


def _default_mapping(cands: dict) -> tuple[dict, dict | None]:
    inputs: dict[str, dict] = {}
    used: set[str] = set()

    def add(c: dict, key: str) -> None:
        n = 2
        base = key
        while key in used:
            key, n = f"{base}{n}", n + 1
        used.add(key)
        inputs[key] = {k: c[k] for k in ("node", "field", "kind", "role", "media", "title", "min", "max", "step") if k in c}
        inputs[key]["default"] = c["value"]

    media = [c for c in cands["inputs"] if c["role"] == "media"]
    for c in media:
        add(c, "media")
    prompts = [c for c in cands["inputs"] if c["role"] == "prompt"]
    if prompts:  # the first prompt that is not a negative one
        add(next((c for c in prompts if "neg" not in c["title"].lower()), prompts[0]), "prompt")
    for c in cands["inputs"]:
        if c["role"] == "seed":
            add(c, "seed")
    outs = cands["outputs"]
    output = next((o for o in outs if o["classType"].startswith("Save") or "Combine" in o["classType"]), outs[0] if outs else None)
    return inputs, ({"node": output["node"], "type": output["type"]} if output else None)


def _write_sidecar(d: Path, meta: dict) -> None:
    side = {"workflow": "graph.api.json", "description": meta["name"],
            "inputs": {k: {"node": v["node"], "field": v["field"], "kind": v["kind"], "optional": True}
                       for k, v in meta["inputs"].items()},
            "outputs": {"result": {"node": meta["output"]["node"], "type": meta["output"].get("type", "image")}} if meta.get("output") else {}}
    write_json_atomic(d / SIDE, side)


# ---- CRUD -------------------------------------------------------------------------

def _readiness(meta: dict, graph: dict, registry: dict) -> dict:
    """Recheck node/model availability without requiring a reimport after installing models."""
    meta = {**meta, "inputs": _model_inputs(meta, graph, registry)}
    if not registry:
        return {**meta, "readinessError": "Cannot reach ComfyUI. Check the connection and try again."}
    missing_models = set()
    for node in graph.values():
        spec = (registry.get(node["class_type"]) or {}).get("input") or {}
        fields = {**spec.get("required", {}), **spec.get("optional", {})}
        for key, value in node.get("inputs", {}).items():
            choices = fields.get(key) or [None]
            if key in MODEL_FIELDS and isinstance(value, str) and isinstance(choices[0], list) and value not in choices[0]:
                missing_models.add(value)
    return {**meta, "readinessError": None, "missing": sorted({n["class_type"] for n in graph.values() if n["class_type"] not in registry}),
            "missingModels": sorted(missing_models)}


def _model_inputs(meta: dict, graph: dict, registry: dict) -> dict:
    """Expose loaders even for older imports; choices always belong to the selected host."""
    inputs = copy.deepcopy(meta["inputs"])
    for nid, node in graph.items():
        spec = (registry.get(node["class_type"]) or {}).get("input") or {}
        fields = {**spec.get("required", {}), **spec.get("optional", {})}
        for field, value in node.get("inputs", {}).items():
            if field not in MODEL_FIELDS or not isinstance(value, str):
                continue
            key = next((k for k, v in inputs.items() if v["node"] == nid and v["field"] == field), None)
            if key is None:
                key = f"model.{nid}.{field}"
                while key in inputs:
                    key += "_"
            options = fields.get(field) or [None]
            inputs[key] = {"node": nid, "field": field, "kind": "string", "role": "model",
                           "title": _title(node, nid), "default": value,
                           "choices": [v for v in options[0] if isinstance(v, str)] if isinstance(options[0], list) else []}
    return inputs


def _target_readiness(meta: dict, graph: dict, remote: bool | None = None) -> dict:
    """Prefer a ready local host, otherwise use the configured remote GPU.

    Explicit targets are never silently changed. The selected target travels with the job.
    """
    if remote is True and remote_runner is None:
        raise WorkflowApiError(400, "Remote generation is not configured")
    meta = {**meta, "targets": [{"id": "local", "label": "My ComfyUI"}] + (
        [{"id": "remote", "label": "Comfy Cloud" if getattr(remote_runner, "cloud", False) else "Remote ComfyUI"}] if remote_runner else [])}
    local = None
    if remote is not True:
        local = {**_readiness(meta, graph, object_info()), "target": "local"}
        if remote is False or remote_runner is None or not any(local.get(k) for k in ("missing", "missingModels", "readinessError")):
            return local
    return {**_readiness(meta, graph, object_info(remote=True)), "target": "remote"}


def list_workflows(remote: bool | None = None, refresh: bool = False) -> list[dict]:
    if remote is True and remote_runner is None:
        raise WorkflowApiError(400, "Remote generation is not configured")
    if refresh:
        object_info(force=True, remote=remote is True)
    out = []
    for f in sorted(root().glob("*/workflow.json")):
        try:
            out.append(get_workflow(f.parent.name, remote))
        except Exception:
            continue
    out.sort(key=lambda m: m.get("createdAt", ""), reverse=True)
    return out


def get_workflow(wid: str, remote: bool | None = None, inputs: dict | None = None) -> dict:
    d = _dir(wid)
    meta = json.loads((d / "workflow.json").read_text(encoding="utf-8"))
    graph = json.loads((d / "graph.api.json").read_text(encoding="utf-8"))
    for key, spec in _model_inputs(meta, graph, {}).items():
        if spec.get("role") == "model" and inputs and key in inputs:
            value = inputs[key]
            if not isinstance(value, str) or not value.strip():
                raise WorkflowApiError(422, f"Choose a model for {spec['title']}")
            graph[spec["node"]]["inputs"][spec["field"]] = value
    return _target_readiness(meta, graph, remote)


def import_workflow(body: dict) -> dict:
    """body: {name?, graph (API format, or a file's parsed JSON), ui? (UI format, kept for editing), source?}"""
    raw = body.get("graph")
    graph = api_graph(raw)
    if graph is None:
        ui = raw if isinstance(raw, dict) and "nodes" in raw else None
        raise WorkflowApiError(422, "This is an editor (UI) workflow: open it in ComfyUI and use the typeset sidebar's import, or File > Export (API)."
                               if ui else "Not a Comfy workflow (expected API-format JSON)")
    registry = object_info(force=True)
    missing = sorted({n["class_type"] for n in graph.values() if registry and n["class_type"] not in registry})
    cands = candidates(graph, registry)
    inputs, output = _default_mapping(cands)
    wid = uuid.uuid4().hex[:12]
    d = root() / wid
    d.mkdir(parents=True, exist_ok=True)
    write_json_atomic(d / "graph.api.json", graph)
    if isinstance(body.get("ui"), dict):
        write_json_atomic(d / "ui.json", body["ui"])
    name = str(body.get("name") or "").strip() or next((c["classType"] for c in cands["outputs"]), "workflow")
    meta = {"id": wid, "name": name[:80], "createdAt": _now(), "source": body.get("source") or "file",
            "nodes": len(graph), "missing": missing, "candidates": cands, "inputs": inputs, "output": output}
    write_json_atomic(d / "workflow.json", meta)
    if output:
        _write_sidecar(d, meta)
    return _target_readiness(meta, graph)


def update_workflow(wid: str, body: dict) -> dict:
    """body: {name?, inputs?: {key: {node, field, ...}}, output?: {node, type}} — only graph nodes allowed."""
    d = _dir(wid)
    meta = json.loads((d / "workflow.json").read_text(encoding="utf-8"))
    graph = json.loads((d / "graph.api.json").read_text(encoding="utf-8"))
    if "name" in body and str(body["name"]).strip():
        meta["name"] = str(body["name"]).strip()[:80]
    if "inputs" in body:
        by = {(c["node"], c["field"]): c for c in meta["candidates"]["inputs"]}
        for v in _model_inputs(meta, graph, {}).values():
            if v.get("role") == "model":
                by[(v["node"], v["field"])] = {**v, "value": v["default"]}
        inputs = {}
        for key, spec in (body.get("inputs") or {}).items():
            c = by.get((str(spec.get("node")), str(spec.get("field"))))
            if c is None or not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", key):
                raise WorkflowApiError(422, f"Unknown input {key}")
            inputs[key] = {k: c[k] for k in ("node", "field", "kind", "role", "media", "title", "min", "max", "step") if k in c}
            inputs[key]["default"] = spec.get("default", c["value"])
        meta["inputs"] = inputs
    if "output" in body:
        o = body.get("output") or {}
        if str(o.get("node")) not in graph:
            raise WorkflowApiError(422, "Output node is not in the graph")
        cand = next((c for c in meta["candidates"]["outputs"] if c["node"] == str(o["node"])), None)
        meta["output"] = {"node": str(o["node"]), "type": o.get("type") or (cand or {}).get("type", "image")}
    write_json_atomic(d / "workflow.json", meta)
    if meta.get("output"):
        _write_sidecar(d, meta)
    return get_workflow(wid)


def delete_workflow(wid: str) -> dict:
    shutil.rmtree(_dir(wid))
    return {"deleted": wid}


# ---- current project (for ComfyUI's "add to <project>") ----------------------------

def _session_file() -> Path:
    return settings.data_dir / "session.json"


def set_current_project(pid: str, name: str | None = None) -> dict:
    data = {"projectId": pid, "name": name, "at": _now()}
    write_json_atomic(_session_file(), data)
    return data


def current_project() -> dict:
    try:
        return json.loads(_session_file().read_text(encoding="utf-8"))
    except Exception:
        return {"projectId": None}


# ---- run ------------------------------------------------------------------------------

def _asset(project, asset_id: str) -> dict | None:
    for a in getattr(project, "assets", None) or []:
        a = a.model_dump(mode="json") if hasattr(a, "model_dump") else a
        if a.get("id") == asset_id:
            return a
    return None


def _stage_media(store, project, spec: dict, src: dict, work: Path, stage) -> tuple[str, dict]:
    """Make the chosen source into a file ComfyUI can load. Returns (input path, provenance)."""
    from .pipeline import project_path
    pid = project.id
    want = spec.get("media", "image")
    asset = _asset(project, src["assetId"]) if src.get("assetId") else None
    if src.get("assetId") and asset is None:
        raise WorkflowApiError(404, "Source asset not found")
    tag = uuid.uuid4().hex[:8]
    if want == "audio":
        # A song window for audio-driven generators (S2V, H3 guide, lip-sync). start/end are PROJECT seconds;
        # the project song is mapped through media.audioClip (song [in,out) plays from project time offset).
        from .audioclip import clip_of
        a = max(0.0, float(src.get("start") if src.get("start") is not None else 0))
        b = float(src.get("end")) if src.get("end") is not None else a + 5.0
        b = min(b, a + MAX_RANGE) if b > a else a + min(5.0, MAX_RANGE)
        if src.get("path"):
            apath, aprov, sa = project_path(store, pid, src["path"]), {"path": src["path"]}, a
        elif asset:
            apath, aprov, sa = project_path(store, pid, asset["path"]), {"assetId": asset["id"]}, a
        elif project.media.audio or project.media.video:
            m = project.media.audio or project.media.video
            c = clip_of(project)
            apath, aprov, sa = project_path(store, pid, m.path), {"audio": m.path}, a + ((c["in"] - c["offset"]) if c else 0.0)
        else:
            raise WorkflowApiError(400, "Add a song (or pick an asset with sound) first")
        out = work / f"{tag}.wav"
        work.mkdir(parents=True, exist_ok=True)
        ffmpeg(["-ss", f"{max(0.0, sa):.3f}", "-i", apath, "-t", f"{b - a:.3f}", "-vn", "-ac", "2", "-ar", "48000", out], what="ffmpeg(workflow audio)")
        return stage(out, pid, "wf", out.name), {**aprov, "start": round(a, 3), "end": round(b, 3), "songStart": round(sa, 3)}
    if asset:
        path, is_video, prov = project_path(store, pid, asset["path"]), asset.get("kind") == "video", {"assetId": asset["id"]}
    elif project.media.video:
        path, is_video, prov = project_path(store, pid, project.media.video.path), True, {"video": project.media.video.path}
    else:
        raise WorkflowApiError(400, "Pick an asset or add footage first")
    if not is_video:
        return stage(path, pid, "wf", f"{tag}{path.suffix.lower()}"), prov
    dur = float((asset or {}).get("duration") or project.duration or 0)
    if want == "image":
        t = max(0.0, min(float(src.get("time") or 0), max(0.0, dur - 1 / max(project.fps, 1))))
        out = extract_frame(path, t, work / f"{tag}.png")
        return stage(out, pid, "wf", out.name), {**prov, "time": round(t, 3)}
    a = max(0.0, float(src.get("start") if src.get("start") is not None else 0))
    b = float(src.get("end") if src.get("end") is not None else dur or a + 5)
    b = min(b, a + MAX_RANGE) if b > a else a + min(5.0, MAX_RANGE)
    out = work / f"{tag}.mp4"
    work.mkdir(parents=True, exist_ok=True)
    ffmpeg(["-ss", f"{a:.3f}", "-i", path, "-t", f"{b - a:.3f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", out],
           what="ffmpeg(workflow range)")
    return stage(out, pid, "wf", out.name), {**prov, "start": round(a, 3), "end": round(b, 3)}


def _single_file(files: list[Path], fps: float, work: Path) -> Path:
    """One output file per run: several stills (a frame batch) become a video at project fps."""
    vids = [f for f in files if f.suffix.lower() in VIDEO_EXT]
    if vids:
        return vids[0]
    imgs = [f for f in files if f.suffix.lower() in IMAGE_EXT]
    if not imgs:
        raise WorkflowApiError(500, "The output node produced no image or video file")
    if len(imgs) == 1:
        return imgs[0]
    seq = work / "seq"
    seq.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(sorted(imgs)):
        shutil.copy2(f, seq / f"{i:05d}{imgs[0].suffix.lower()}")
    out = work / "batch.mp4"
    ffmpeg(["-framerate", f"{fps:g}", "-i", seq / f"%05d{imgs[0].suffix.lower()}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", out],
           what="ffmpeg(workflow frames)")
    return out


def check_run(service, pid: str, wid: str, body: dict) -> dict:
    project = service.require_project(pid)
    meta = get_workflow(wid, remote=body.get("remote"), inputs=body.get("inputs"))
    if not meta.get("output"):
        raise WorkflowApiError(400, "Choose the workflow's output first")
    if meta.get("readinessError"):
        raise WorkflowApiError(503, meta["readinessError"])
    if meta.get("missing"):
        raise WorkflowApiError(400, "ComfyUI is missing nodes: " + ", ".join(meta["missing"]))
    if meta.get("missingModels"):
        raise WorkflowApiError(400, "ComfyUI is missing models: " + ", ".join(meta["missingModels"]))
    if body.get("takeOf") and not any((l.get("id") if isinstance(l, dict) else getattr(l, "id", None)) == body["takeOf"]
                                      for l in getattr(project, "layers", None) or []):
        raise WorkflowApiError(404, "Layer not found")
    from .pipeline import project_path
    for key, src in (body.get("sources") or {}).items():
        if src.get("path"):
            if meta["inputs"].get(key, {}).get("media") != "audio":
                raise WorkflowApiError(400, "Prepared files are supported for audio inputs only")
            try:
                path = project_path(service.store, pid, src["path"])
                if not path.is_file(): raise ValueError("Prepared vocal file is missing")
            except (ValueError, TypeError) as exc:
                raise WorkflowApiError(400, str(exc)) from exc
    pp = body.get("postprocess")
    if pp:
        if meta["output"].get("type") != "video":
            raise WorkflowApiError(400, "Output retiming requires a video workflow")
        try:
            for key, lo, hi in (("timeScale", .5, 2), ("trimStart", 0, 2), ("fps", 1, 60)):
                v = float(pp[key])
                if not math.isfinite(v) or not lo <= v <= hi: raise ValueError(f"Invalid output {key}")
            if pp.get("audio") and not project_path(service.store, pid, pp["audio"]).is_file():
                raise ValueError("Output soundtrack is missing")
        except (ValueError, TypeError, KeyError) as exc:
            raise WorkflowApiError(400, str(exc)) from exc
    return meta


def _retime_output(store, pid: str, out: Path, work: Path, settings: dict) -> Path:
    """Return a prepared-drive S2V output to the original song's time and frame rate."""
    from .pipeline import project_path
    result = work / f"retimed_{uuid.uuid4().hex[:8]}.mp4"
    vf = (f"setpts={float(settings['timeScale']):.6f}*PTS,"
          f"minterpolate=fps={float(settings['fps']):g}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
          f"trim=start={float(settings['trimStart']):.6f},setpts=PTS-STARTPTS")
    args = ["-i", out]
    if settings.get("audio"):
        args += ["-i", project_path(store, pid, settings["audio"]), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "256k", "-shortest"]
    else:
        args += ["-an"]
    ffmpeg(args + ["-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", result], what="ffmpeg(workflow vocal retiming)")
    return result


def run_job(service, pid: str, wid: str, body: dict):
    meta = check_run(service, pid, wid, body)
    body = {**body, "remote": meta["target"] == "remote"}
    job = service.jobs.create("workflow", pid)
    return service.jobs.submit(job, lambda ctx: run_workflow(service, pid, wid, body, ctx))


MAX_VARIANTS = 8


def run_workflow(service, pid: str, wid: str, body: dict, ctx) -> dict:
    """body: {inputs: {key: value}, source?: WfSource (every media input), sources?: {key: WfSource},
    variants?: n (n seeds, one asset each), layerId?: provenance-only layer id,
    addLayer?: bool|'top', takeOf?: layerId, remote?: bool, postprocess?: {timeScale, trimStart, fps, audio?}}
    WfSource = {assetId?, path? (prepared audio), time?, start?, end?}. Several variants only fill the bin; the studio picks one."""
    store = service.store
    project = service.require_project(pid)
    meta = check_run(service, pid, wid, body)
    d = _dir(wid)
    run = remote_runner if meta["target"] == "remote" else runner
    n = max(1, min(MAX_VARIANTS, int(body.get("variants") or 1)))
    run_id = uuid.uuid4().hex[:10]
    work = store.project_dir(pid) / "cache" / "workflows" / run_id
    work.mkdir(parents=True, exist_ok=True)
    side = d / SIDE
    if any(s.get("role") == "model" for s in meta["inputs"].values()):
        # Bind model choices per run. Never rewrite the shared graph or another scene's recipe.
        write_json_atomic(work / "graph.api.json", json.loads((d / "graph.api.json").read_text(encoding="utf-8")))
        _write_sidecar(work, meta)
        side = work / SIDE
    values: dict[str, Any] = {}
    given = body.get("inputs") or {}
    sources = body.get("sources") or {}
    prov: dict[str, Any] = {}
    seeds = [k for k, s in meta["inputs"].items() if s.get("role") == "seed"]
    for key, spec in meta["inputs"].items():
        v = given.get(key, spec.get("default") if spec.get("role") == "model" else None)
        if spec.get("role") == "media":
            if v in (None, ""):
                ctx.progress(.02, "staging source")
                v, prov[key] = _stage_media(store, project, spec, sources.get(key) or body.get("source") or {}, work, run.stage_image)
            values[key] = v
        elif spec.get("role") == "seed" and (v is None or v == "" or int(float(v)) < 0):
            values[key] = random.randint(0, 2**31 - 1)
        elif v is not None:
            values[key] = v
    out_assets: list[dict] = []
    timing: dict = {}
    for i in range(n):
        vals = dict(values)
        if i:  # each further variant is the next seed (or a fresh one when the workflow has none)
            for k in seeds:
                vals[k] = (int(values[k]) + i) % 2**32
        base, span = .05 + .9 * i / n, .9 / n
        label = meta["name"] + (f" {i + 1}/{n}" if n > 1 else "")
        ctx.progress(base, f"{label}: queued")
        result = run.run(str(side), vals, work / f"out{i}",
                         progress=lambda status, el, base=base, label=label: ctx.progress(base + span * min(.95, el / 90), f"{label}: {status} ({el:.0f}s)"))
        out = _single_file(result.outputs.get("result") or [], project.fps or 24, work)
        if body.get("postprocess"):
            ctx.progress(base + span * .97, "Returning the take to song timing")
            out = _retime_output(store, pid, out, work, body["postprocess"])
        seed = next((vals[k] for k in seeds), None)
        source = {"kind": "workflow", "workflowId": wid, "workflowName": meta["name"], "promptId": result.job_id, "runId": run_id,
                  "inputs": vals, "seed": seed, **({"from": prov} if prov else {}),
                  **({"postprocess": body["postprocess"]} if body.get("postprocess") else {}),
                  **({"layerId": body["layerId"]} if body.get("layerId") else {}),
                  **({"sceneId": body["sceneId"]} if body.get("sceneId") else {}), "remote": run is not runner, "at": _now()}
        add = False if (body.get("takeOf") or n > 1) else ("top" if body.get("addLayer") == "top" else bool(body.get("addLayer")))
        name = f"{meta['name']} {seed if seed is not None else run_id[:4]}"
        with out.open("rb") as fh:
            asset = service.add_asset(pid, out.name, iter(lambda: fh.read(1024 * 1024), b""), source, add, name)
        if body.get("takeOf") and n == 1:
            _swap_take(store, pid, body["takeOf"], asset["id"])
        out_assets.append(asset)
        timing = result.timing
        shutil.rmtree(work / "seq", ignore_errors=True)
        (work / "batch.mp4").unlink(missing_ok=True)
        ctx.set_result({"assets": out_assets, "workflowId": wid, "runId": run_id})
    first = out_assets[0]
    return {"asset": first, "assetId": first["id"], "assets": out_assets, "workflowId": wid, "runId": run_id,
            "promptId": first["source"]["promptId"], "timing": timing}


def _swap_take(store, pid: str, layer_id: str, asset_id: str) -> None:
    """Put the new asset into an existing layer as its active take; timing/placement stay as they are."""
    def update(p):
        layers = getattr(p, "layers", None) or []
        for layer in layers:
            get = layer.get if isinstance(layer, dict) else (lambda k, default=None, _l=layer: getattr(_l, k, default))
            if get("id") != layer_id:
                continue
            takes = list(get("takes") or [get("assetId")])
            if asset_id not in takes:
                takes.append(asset_id)
            if isinstance(layer, dict):
                layer["takes"], layer["assetId"] = takes, asset_id
            else:
                setattr(layer, "takes", takes)
                setattr(layer, "assetId", asset_id)
    store.update(pid, update)
