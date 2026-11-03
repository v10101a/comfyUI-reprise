"""Reprise API logic, independent of the web framework.

`main.py` (FastAPI, :8787) and `typeset_nodes/studio_host.py` (aiohttp routes inside ComfyUI, /typeset)
are thin adapters over these functions. Errors are `ApiError(status, detail)`.
"""
from __future__ import annotations

import json
import re
import logging
import threading
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .comfy import runner, remote_runner
from .config import settings
from .exporter import export_project, frames_dir
from .jobs import JobManager
from .media import probe_media, safe_filename, fit_within, encode_preview_proxy, proxy_rel
from .models import Project, Job, CreateProjectBody, AnalyzeWordsBody, AnalyzeMatteBody, InworldBody, ExportBody, ReframeBody
from .analysis_v2 import analyze_occupancy, track_surface, reframe_project, analyze_beats, analyze_flow, analyze_voice, analyze_audio
from .pipeline import analyze_words, analyze_matte, generate_inworld, project_path
from .matte_source import matte_source
from .head_tracking import head_sources, analyze_heads
from .store import ProjectStore, ProjectNotFound, write_json_atomic

log = logging.getLogger(__name__)

store = ProjectStore(settings.projects_dir)
jobs = JobManager(settings.jobs_dir)


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def require_project(pid: str) -> Project:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", pid):
        raise ApiError(400, "Invalid project id")
    try:
        return store.load(pid)
    except ProjectNotFound:
        raise ApiError(404, "Project not found") from None


def validate_paths(project: Project):
    refs = [ref.path for ref in (project.media.video, project.media.audio) if ref]
    refs += [p for p in (project.analysis.words, project.analysis.matte, project.analysis.tracks, project.analysis.depth,
                         project.analysis.occupancy, project.analysis.beats, project.analysis.flow,
                         project.analysis.voice, project.analysis.audio) if p]
    refs += [s.track for s in project.surfaces or [] if s.track]
    refs += list(project.analysis.headTracks) + list(project.analysis.headTracks.values())
    if project.frame and project.frame.crop:
        refs.append(project.frame.crop)
    refs += [p for shot in project.shots for p in (shot.plate, shot.video) if p]
    refs += [a.get("path") for a in getattr(project, "assets", None) or [] if isinstance(a, dict) and a.get("path")]
    for ref in refs:
        project_path(store, project.id, ref)


def health() -> dict[str, Any]:
    return {"status": "ok", **runner.health(), "generationTarget": "remote" if remote_runner else "local",
            "remote": remote_runner.health() if remote_runner else None}


def create_project(body: CreateProjectBody) -> Project:
    return store.create(body.name)


def list_projects() -> list[Project]:
    return store.list()


def save_project(pid: str, body: Project) -> Project:
    require_project(pid)
    if body.id != pid:
        raise ApiError(400, "Project id must match URL")
    try:
        validate_paths(body)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    with store.lock(pid):
        current = store.load(pid)
        # Head tracks belong to immutable source media, independent of trim and edit time.
        body.analysis.headTracks = {**body.analysis.headTracks, **current.analysis.headTracks}
        # Analysis can finish in another tab/worker while this editor has an older
        # copy. A same-footage save must not discard completed server assets.
        if (body.media.video == current.media.video and body.width == current.width
                and body.height == current.height and body.fps == current.fps):
            if body.analysis.matte is None and current.analysis.matte:
                # Provenance and all three outputs are one result, never mix sources.
                for key in ("matte", "tracks", "occupancy", "matteSource"):
                    setattr(body.analysis, key, getattr(current.analysis, key))
            for key in ("tracks", "occupancy"):
                if body.analysis.matte == current.analysis.matte and getattr(body.analysis, key) is None and getattr(current.analysis, key):
                    setattr(body.analysis, key, getattr(current.analysis, key))
        # The asset bin is additive: assets added on the server (uploads, workflow outputs) since this editor loaded survive.
        have = {a.get("id") for a in getattr(body, "assets", None) or [] if isinstance(a, dict)}
        extra = [a for a in getattr(current, "assets", None) or [] if isinstance(a, dict) and a.get("id") not in have]
        if extra:
            body.assets = [*(getattr(body, "assets", None) or []), *extra]
            # ...and so do layers made with them (addLayer), at their stack position when the body's stack allows.
            new_ids = {a.get("id") for a in extra}
            cur_layers = getattr(current, "layers", None) or []
            fresh = [(i, l) for i, l in enumerate(cur_layers) if isinstance(l, dict) and l.get("assetId") in new_ids]
            if fresh:
                layers = [dict(l) for l in (getattr(body, "layers", None) or DEFAULT_LAYERS)]
                for i, l in fresh:
                    layers.insert(min(i, len(layers)), l)
                body.layers = layers
        return store.save(body)



def _make_video_proxy(src: Path, out: Path) -> None:
    """Studio preview proxy (media.py), off the request thread; the studio reads the original until it exists."""
    def run():
        try:
            encode_preview_proxy(src, out)
            encode_preview_proxy(src, out.with_name(out.stem + ".full.mp4"), full=True)
        except Exception as exc:  # non-fatal: scrubbing just stays slow for this clip
            log.warning("preview proxy failed for %s: %s", src.name, exc)
    threading.Thread(target=run, name="typeset-proxy", daemon=True).start()

def upload_media(pid: str, filename: str, kind: str, chunks: Iterable[bytes]):
    """kind=reference stores an identity reference image for generate/inworld (`referenceImage`) and
    returns {path, width, height}; it does not change the project's media."""
    if kind not in ("video", "audio", "reference"):
        raise ApiError(422, "kind must be video, audio or reference")
    require_project(pid)
    name = f"{uuid.uuid4().hex[:12]}_{safe_filename(filename or 'upload')}"
    rel = f"media/{name}"
    path = project_path(store, pid, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    limit = 50 * 1024**2 if kind == "reference" else 4 * 1024**3
    try:
        with path.open("wb") as target:
            for chunk in chunks:
                count += len(chunk)
                if count > limit:
                    raise ApiError(413, f"Uploads are limited to {'50 MiB' if kind == 'reference' else '4 GiB'}")
                target.write(chunk)
        if kind == "reference":
            from PIL import Image
            try:
                with Image.open(path) as im:
                    im.verify()
                with Image.open(path) as im:
                    w, h = im.size
            except Exception:
                raise ApiError(400, "Reference must be an image (PNG, JPEG or WebP)")
            return {"path": rel, "width": w, "height": h}
        ref = probe_media(path, rel)
        if ref.duration <= 0 or (kind == "video" and not ref.width) or (kind == "audio" and not ref.hasAudio):
            raise ApiError(400, f"File is not playable {kind} media")
        def update(p):
            # A new song (or the video that carries it) invalidates the song clip.
            if kind == "audio" or not p.media.audio:
                setattr(p.media, "audioClip", None)
            setattr(p.media, kind, ref)
            if kind == "video":
                p.width, p.height = fit_within(ref.width, ref.height)
                p.fps = min(60., ref.fps or 24.)
                p.duration = ref.duration
                # Old mattes/tracks belong to old footage.
                p.analysis.matte = p.analysis.tracks = p.analysis.occupancy = p.analysis.matteSource = None
                p.analysis.headTracks = {}
                p.shots = []
            elif not p.media.video:
                p.duration = ref.duration
        store.update(pid, update)
        if kind == "video":
            _make_video_proxy(path, project_path(store, pid, proxy_rel(rel)))
        return ref
    except ApiError:
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise ApiError(400, f"Cannot read uploaded media: {exc}") from exc


# ---- asset bin + layer stack (docs/SCHEMA.md §1 assets/layers) -------------------------

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
# The implied stack of a project without `layers` (renderer.ts DEFAULT_LAYERS): plate, behind text, subject, front text.
DEFAULT_LAYERS = [{"id": "plate", "kind": "plate"}, {"id": "text-behind", "kind": "text", "which": "behind"},
                  {"id": "subject", "kind": "subject"}, {"id": "text-front", "kind": "text", "which": "front"}]


def _probe_asset(path: Path, rel: str) -> dict[str, Any]:
    """{kind, path, width, height[, duration, fps, hasAudio]} for an image or a playable video; ApiError otherwise."""
    if path.suffix.lower() in IMAGE_EXTS:
        from PIL import Image
        try:
            with Image.open(path) as im:
                w, h = im.size
        except Exception:
            raise ApiError(400, "File is not a readable image") from None
        return {"kind": "image", "path": rel, "width": w, "height": h}
    ref = probe_media(path, rel)
    if ref.duration <= 0 or not ref.width:
        raise ApiError(400, "File is not playable video or a readable image")
    return {"kind": "video", "path": rel, "duration": ref.duration, "width": ref.width, "height": ref.height,
            "fps": ref.fps, "hasAudio": ref.hasAudio}


def _comfy_file(ref: dict) -> Path:
    """A ComfyUI output/input/temp file as /view addresses it ({filename, subfolder, type})."""
    try:
        filename, kind = str(ref["filename"]), str(ref.get("type") or "output")
    except Exception:
        raise ApiError(422, "comfy needs {filename, subfolder, type}") from None
    if kind not in ("output", "input", "temp"):
        raise ApiError(422, "comfy.type must be output, input or temp")
    try:  # inside ComfyUI (studio_host) its own folders win, including --output-directory
        import folder_paths
        base = Path(folder_paths.get_directory_by_type(kind) or "")
    except Exception:
        base = settings.comfy_dir / kind
    base = base.resolve()
    src = (base / str(ref.get("subfolder") or "") / filename).resolve()
    if not base.is_dir() or not src.is_relative_to(base) or not src.is_file():
        raise ApiError(404, f"No such ComfyUI file: {filename}")
    return src


def add_asset(pid: str, filename: str, chunks: Iterable[bytes], source: dict | None = None,
              add_layer: bool | str = False, name: str | None = None) -> dict[str, Any]:
    """Store a video/image in the project's asset bin (never replaces media.video). add_layer: true/'under-text' puts a
    media layer just under the behind-text marker (a new background), 'top' on top of the stack. Returns the Asset
    (plus `layer` when one was added)."""
    require_project(pid)
    aid = "a_" + uuid.uuid4().hex[:10]
    rel = f"media/{aid}_{safe_filename(filename or 'asset')}"
    path = project_path(store, pid, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with path.open("wb") as target:
            for chunk in chunks:
                count += len(chunk)
                if count > 4 * 1024**3:
                    raise ApiError(413, "Uploads are limited to 4 GiB")
                target.write(chunk)
        asset = {"id": aid, **_probe_asset(path, rel), "name": name or Path(filename or rel).stem,
                 "source": source or {"kind": "upload"}}
        asset = {k: v for k, v in asset.items() if v is not None}
        layer = None
        if add_layer:
            layer = {"id": "l_" + uuid.uuid4().hex[:10], "kind": "media", "assetId": aid, "name": asset["name"],
                     "start": 0.0, "in": 0.0}

        def update(p):
            assets = list(getattr(p, "assets", None) or [])
            assets.append(asset)
            p.assets = assets
            if layer is None:
                return
            layer["out"] = round(min(asset.get("duration") or p.duration or 10.0, p.duration or 1e9), 3)
            layers = [dict(l) for l in (getattr(p, "layers", None) or DEFAULT_LAYERS)]
            at = len(layers)
            if add_layer != "top":
                at = next((i for i, l in enumerate(layers) if l.get("kind") == "text" and l.get("which") == "behind"), at)
            layers.insert(at, layer)
            p.layers = layers
        store.update(pid, update)
        if asset["kind"] == "video":
            _make_video_proxy(path, project_path(store, pid, proxy_rel(rel)))
        return {**asset, "layer": layer} if layer else asset
    except ApiError:
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise ApiError(400, f"Cannot read asset: {exc}") from exc


def add_comfy_asset(pid: str, comfy: dict, add_layer: bool | str = False, source: dict | None = None,
                    name: str | None = None) -> dict[str, Any]:
    """POST /assets with JSON {comfy:{filename,subfolder,type}, addLayer?, source?, name?}: copy a ComfyUI file in."""
    src = _comfy_file(comfy)
    prov = {"kind": "comfy", "filename": src.name, "subfolder": comfy.get("subfolder") or "", "type": comfy.get("type") or "output",
            **(source or {})}
    with src.open("rb") as fh:
        return add_asset(pid, src.name, iter(lambda: fh.read(1024 * 1024), b""), prov, add_layer, name)


def assets_json(pid: str, data: dict) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("comfy"), dict):
        raise ApiError(422, "Expected multipart file or JSON {comfy:{filename,subfolder,type}}")
    return add_comfy_asset(pid, data["comfy"], data.get("addLayer") or False,
                           data.get("source") if isinstance(data.get("source"), dict) else None, data.get("name"))


def analyze_words_job(pid: str, body: AnalyzeWordsBody) -> Job:
    project = require_project(pid)
    if not (project.media.audio or project.media.video):
        raise ApiError(400, "Upload audio or video first")
    job = jobs.create("words", pid)
    return jobs.submit(job, lambda ctx: analyze_words(store, pid, body.language or "auto", ctx))


def analyze_matte_job(pid: str, body: AnalyzeMatteBody) -> Job:
    project = require_project(pid)
    try:
        source = matte_source(project, body.layerId)
        if not project_path(store, pid, source["path"]).is_file():
            raise ValueError("The selected matte source file is missing")
    except (ValueError, TypeError) as exc:
        raise ApiError(400, str(exc)) from exc
    job = jobs.create("matte", pid, "Preparing subject matte")
    job.layerId = body.layerId
    return jobs.submit(job, lambda ctx: analyze_matte(store, pid, ctx, source=source))


def analyze_heads_job(pid: str) -> Job:
    sources = head_sources(require_project(pid))
    if not sources:
        raise ApiError(400, 'Add footage to the timeline first')
    for source in sources:
        if not project_path(store, pid, source['path']).is_file():
            raise ApiError(400, 'A head tracking source file is missing')
    job = jobs.create('heads', pid, 'Tracking heads')
    return jobs.submit(job, lambda ctx: analyze_heads(store, pid, ctx, sources))


def inworld_job(pid: str, body: InworldBody) -> Job:
    project = require_project(pid)
    if body.end <= body.start or body.start < 0 or body.end > project.duration + .001 or body.end - body.start > 10:
        raise ApiError(400, "Choose a range within the project, between zero and ten seconds long")
    if not project.media.video or not body.wordIds or not set(body.wordIds) <= {w.id for w in project.words}:
        raise ApiError(400, "Upload video and select existing words first")
    job = jobs.create("inworld", pid)
    return jobs.submit(job, lambda ctx: generate_inworld(store, pid, body, ctx),
                       lane="remote" if body.engine == "remote-minimax" else None)


def occupancy_job(pid: str) -> Job:
    project = require_project(pid)
    if not project.analysis.matte:
        raise ApiError(400, "Run foreground extraction (matte) first")
    job = jobs.create("occupancy", pid)
    return jobs.submit(job, lambda ctx: analyze_occupancy(store, pid, ctx))


def beats_job(pid: str) -> Job:
    project = require_project(pid)
    if not (project.media.audio or project.media.video):
        raise ApiError(400, "Upload audio or video first")
    job = jobs.create("beats", pid)
    return jobs.submit(job, lambda ctx: analyze_beats(store, pid, ctx))


def flow_job(pid: str) -> Job:
    project = require_project(pid)
    if not project.media.video:
        raise ApiError(400, "Upload video first")
    job = jobs.create("flow", pid)
    return jobs.submit(job, lambda ctx: analyze_flow(store, pid, ctx))


def voice_job(pid: str) -> Job:
    project = require_project(pid)
    if not (project.media.audio or project.media.video):
        raise ApiError(400, "Upload audio or video first")
    job = jobs.create("voice", pid)
    return jobs.submit(job, lambda ctx: analyze_voice(store, pid, ctx))


def audio_job(pid: str) -> Job:
    project = require_project(pid)
    if not (project.media.audio or project.media.video):
        raise ApiError(400, "Upload audio or video first")
    job = jobs.create("audio", pid)
    return jobs.submit(job, lambda ctx: analyze_audio(store, pid, ctx))


def surface_track_job(pid: str, sid: str) -> Job:
    project = require_project(pid)
    if not project.media.video:
        raise ApiError(400, "Upload video first")
    if not any(s.id == sid for s in project.surfaces or []):
        raise ApiError(404, "Surface not found; save it in project.surfaces first (PUT)")
    job = jobs.create("surface", pid)
    return jobs.submit(job, lambda ctx: track_surface(store, pid, sid, ctx))


def reframe_job(pid: str, body: ReframeBody) -> Job:
    project = require_project(pid)
    if not project.media.video or project.duration <= 0:
        raise ApiError(400, "Upload video first")
    job = jobs.create("reframe", pid)
    return jobs.submit(job, lambda ctx: reframe_project(store, pid, body.aspect, body.name, ctx, body.focus))


def export_job(pid: str, body: ExportBody) -> Job:
    project = require_project(pid)
    if not body.formats or project.duration <= 0:
        raise ApiError(400, "Choose export formats and a non-empty project")
    if body.frames and not frames_dir(store, pid, body.frames).is_dir():
        raise ApiError(404, "Unknown export session")
    job = jobs.create("export", pid)
    return jobs.submit(job, lambda ctx: export_project(store, pid, body, ctx))


def start_frames(pid: str) -> dict[str, str]:
    """Open an upload session for browser-rendered export frames."""
    require_project(pid)
    session = uuid.uuid4().hex[:12]
    frames_dir(store, pid, session).mkdir(parents=True, exist_ok=True)
    return {"session": session}


def put_frame(pid: str, session: str, layer: str, index: int, data: bytes) -> dict[str, int]:
    if not re.fullmatch(r"[a-f0-9]{12}", session) or layer not in ("text", "composite") or not 0 <= index < 1_000_000:
        raise ApiError(400, "Bad frame address")
    root = frames_dir(store, pid, session)
    if not root.is_dir():
        raise ApiError(404, "Unknown export session")
    if not data.startswith(b"\x89PNG"):
        raise ApiError(400, "Frames must be PNG")
    (root / layer).mkdir(exist_ok=True)
    (root / layer / f"frame_{index:05d}.png").write_bytes(data)
    return {"index": index}


def get_job(job_id: str) -> Job:
    job = jobs.get(job_id)
    if job is None:
        raise ApiError(404, "Job not found")
    return job


def list_jobs(project_id: str | None = None) -> list[Job]:
    return jobs.list(project_id)


# ---- saved looks (named look recipes, shared by every project) --------------------
# A recipe is a look ref only ({id, overrides}): never the song, placement or references.
# Seeded with Dreamy (a hidden preset) and the featured angel recipe so they stay recoverable.
_SEED_LOOKS = [
    {"id": "dreamy", "name": "Dreamy", "ref": {"id": "dreamy", "overrides": {"verse": {"max": 0.09, "keepPosition": True}}}},
]


def _saved_looks_path():
    return settings.data_dir / "looks" / "saved.json"


def saved_looks() -> list[dict[str, Any]]:
    path = _saved_looks_path()
    if not path.exists():
        seed = list(_SEED_LOOKS)
        angel = settings.projects_dir / "b678f509-ca77-4423-a0a6-739869cb0030" / "project.json"
        if angel.exists():
            look = json.loads(angel.read_text()).get("look")
            if look:
                seed.append({"id": "angel", "name": "Angel", "ref": look})
        return seed
    return json.loads(path.read_text())


def set_saved_looks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not all(isinstance(x, dict) and x.get("id") and x.get("name") and isinstance(x.get("ref"), dict) for x in items):
        raise ApiError(422, "expected [{id, name, ref:{id, overrides}}]")
    path = _saved_looks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, items)
    return items


def shutdown() -> None:
    jobs.shutdown()
    runner.reset_client()
    if remote_runner is not None:
        remote_runner.reset_client()
