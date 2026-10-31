"""Typeset API logic, independent of the web framework.

`main.py` (FastAPI, :8787) and `typeset_nodes/studio_host.py` (aiohttp routes inside ComfyUI, /typeset)
are thin adapters over these functions. Errors are `ApiError(status, detail)`.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from typing import Any

from .comfy import runner, remote_runner
from .config import settings
from .exporter import export_project, frames_dir
from .jobs import JobManager
from .media import probe_media, safe_filename, fit_within
from .models import Project, Job, CreateProjectBody, AnalyzeWordsBody, AnalyzeMatteBody, InworldBody, ExportBody, ReframeBody
from .analysis_v2 import analyze_occupancy, track_surface, reframe_project, analyze_beats, analyze_flow, analyze_voice
from .pipeline import analyze_words, analyze_matte, generate_inworld, project_path
from .store import ProjectStore, ProjectNotFound

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
                         project.analysis.voice) if p]
    refs += [s.track for s in project.surfaces or [] if s.track]
    if project.frame and project.frame.crop:
        refs.append(project.frame.crop)
    refs += [p for shot in project.shots for p in (shot.plate, shot.video) if p]
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
    return store.save(body)


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
            setattr(p.media, kind, ref)
            if kind == "video":
                p.width, p.height = fit_within(ref.width, ref.height)
                p.fps = min(60., ref.fps or 24.)
                p.duration = ref.duration
                # Old mattes/tracks belong to old footage.
                p.analysis.matte = p.analysis.tracks = None
                p.shots = []
            elif not p.media.video:
                p.duration = ref.duration
        store.update(pid, update)
        return ref
    except ApiError:
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise ApiError(400, f"Cannot read uploaded media: {exc}") from exc


def analyze_words_job(pid: str, body: AnalyzeWordsBody) -> Job:
    project = require_project(pid)
    if not (project.media.audio or project.media.video):
        raise ApiError(400, "Upload audio or video first")
    job = jobs.create("words", pid)
    return jobs.submit(job, lambda ctx: analyze_words(store, pid, body.language or "auto", ctx))


def analyze_matte_job(pid: str, body: AnalyzeMatteBody) -> Job:
    project = require_project(pid)
    if not project.media.video:
        raise ApiError(400, "Upload video first")
    job = jobs.create("matte", pid)
    return jobs.submit(job, lambda ctx: analyze_matte(store, pid, ctx))


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


def shutdown() -> None:
    jobs.shutdown()
    runner.reset_client()
    if remote_runner is not None:
        remote_runner.reset_client()
