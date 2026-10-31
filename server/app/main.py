"""Typeset local API. Run: server/.venv/bin/uvicorn app.main:app --app-dir server --port 8787"""
from __future__ import annotations

import logging
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .comfy import runner, remote_runner
from .config import settings
from .exporter import export_project
from .jobs import JobManager
from .media import probe_media, safe_filename, fit_within
from .models import Project, CreateProjectBody, AnalyzeWordsBody, AnalyzeMatteBody, InworldBody, ExportBody, ReframeBody
from .analysis_v2 import analyze_occupancy, track_surface, reframe_project, analyze_beats
from .pipeline import analyze_words, analyze_matte, generate_inworld, project_path
from .store import ProjectStore, ProjectNotFound

log = logging.getLogger("typeset")
store = ProjectStore(settings.projects_dir)
jobs = JobManager(settings.jobs_dir)


@asynccontextmanager
async def lifespan(app):
    yield
    jobs.shutdown()
    runner.reset_client()
    if remote_runner is not None:
        remote_runner.reset_client()


app = FastAPI(title="Typeset", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type"])


@app.exception_handler(ProjectNotFound)
async def missing_project(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Project not found"})


def require_project(pid: str) -> Project:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", pid):
        raise HTTPException(400, "Invalid project id")
    return store.load(pid)


def validate_paths(project: Project):
    refs = [ref.path for ref in (project.media.video, project.media.audio) if ref]
    refs += [p for p in (project.analysis.words, project.analysis.matte, project.analysis.tracks, project.analysis.depth,
                         project.analysis.occupancy, project.analysis.beats) if p]
    refs += [s.track for s in project.surfaces or [] if s.track]
    if project.frame and project.frame.crop:
        refs.append(project.frame.crop)
    refs += [p for shot in project.shots for p in (shot.plate, shot.video) if p]
    for ref in refs:
        project_path(store, project.id, ref)


@app.get("/api/health")
def health():
    return {"status": "ok", **runner.health(), "generationTarget": "remote" if remote_runner else "local",
            "remote": remote_runner.health() if remote_runner else None}


@app.post("/api/projects", response_model=Project)
def create_project(body: CreateProjectBody):
    return store.create(body.name)


@app.get("/api/projects", response_model=list[Project])
def list_projects():
    return store.list()


@app.get("/api/projects/{pid}", response_model=Project)
def get_project(pid: str):
    return require_project(pid)


@app.put("/api/projects/{pid}", response_model=Project)
def save_project(pid: str, body: Project):
    require_project(pid)
    if body.id != pid:
        raise HTTPException(400, "Project id must match URL")
    try:
        validate_paths(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return store.save(body)


@app.post("/api/projects/{pid}/media")
def upload_media(pid: str, file: UploadFile = File(...), kind: Literal["video", "audio", "reference"] = Form(...)):
    """kind=reference stores an identity reference image for generate/inworld (`referenceImage`) and
    returns {path, width, height}; it does not change the project's media."""
    require_project(pid)
    name = f"{uuid.uuid4().hex[:12]}_{safe_filename(file.filename or 'upload')}"
    rel = f"media/{name}"
    path = project_path(store, pid, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    limit = 50 * 1024**2 if kind == "reference" else 4 * 1024**3
    try:
        with path.open("wb") as target:
            while chunk := file.file.read(1024 * 1024):
                count += len(chunk)
                if count > limit:
                    raise HTTPException(413, f"Uploads are limited to {'50 MiB' if kind == 'reference' else '4 GiB'}")
                target.write(chunk)
        if kind == "reference":
            from PIL import Image
            try:
                with Image.open(path) as im:
                    im.verify()
                with Image.open(path) as im:
                    w, h = im.size
            except Exception:
                raise HTTPException(400, "Reference must be an image (PNG, JPEG or WebP)")
            return {"path": rel, "width": w, "height": h}
        ref = probe_media(path, rel)
        if ref.duration <= 0 or (kind == "video" and not ref.width) or (kind == "audio" and not ref.hasAudio):
            raise HTTPException(400, f"File is not playable {kind} media")
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
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"Cannot read uploaded media: {exc}") from exc
    finally:
        file.file.close()


@app.post("/api/projects/{pid}/analyze/words")
def words(pid: str, body: AnalyzeWordsBody):
    project = require_project(pid)
    if not (project.media.audio or project.media.video):
        raise HTTPException(400, "Upload audio or video first")
    job = jobs.create("words", pid)
    return jobs.submit(job, lambda ctx: analyze_words(store, pid, body.language or "auto", ctx))


@app.post("/api/projects/{pid}/analyze/matte")
def matte(pid: str, body: AnalyzeMatteBody):
    project = require_project(pid)
    if not project.media.video:
        raise HTTPException(400, "Upload video first")
    job = jobs.create("matte", pid)
    return jobs.submit(job, lambda ctx: analyze_matte(store, pid, ctx))


@app.post("/api/projects/{pid}/generate/inworld")
def inworld(pid: str, body: InworldBody):
    project = require_project(pid)
    if body.end <= body.start or body.start < 0 or body.end > project.duration + .001 or body.end - body.start > 10:
        raise HTTPException(400, "Choose a range within the project, between zero and ten seconds long")
    if not project.media.video or not body.wordIds or not set(body.wordIds) <= {w.id for w in project.words}:
        raise HTTPException(400, "Upload video and select existing words first")
    job = jobs.create("inworld", pid)
    return jobs.submit(job, lambda ctx: generate_inworld(store, pid, body, ctx),
                       lane="remote" if body.engine == "remote-minimax" else None)


@app.post("/api/projects/{pid}/analyze/occupancy")
def occupancy(pid: str):
    project = require_project(pid)
    if not project.analysis.matte:
        raise HTTPException(400, "Run foreground extraction (matte) first")
    job = jobs.create("occupancy", pid)
    return jobs.submit(job, lambda ctx: analyze_occupancy(store, pid, ctx))


@app.post("/api/projects/{pid}/analyze/beats")
def beats(pid: str):
    project = require_project(pid)
    if not (project.media.audio or project.media.video):
        raise HTTPException(400, "Upload audio or video first")
    job = jobs.create("beats", pid)
    return jobs.submit(job, lambda ctx: analyze_beats(store, pid, ctx))


@app.post("/api/projects/{pid}/surfaces/{sid}/track")
def surface_track(pid: str, sid: str):
    project = require_project(pid)
    if not project.media.video:
        raise HTTPException(400, "Upload video first")
    if not any(s.id == sid for s in project.surfaces or []):
        raise HTTPException(404, "Surface not found; save it in project.surfaces first (PUT)")
    job = jobs.create("surface", pid)
    return jobs.submit(job, lambda ctx: track_surface(store, pid, sid, ctx))


@app.post("/api/projects/{pid}/reframe")
def reframe(pid: str, body: ReframeBody):
    project = require_project(pid)
    if not project.media.video or project.duration <= 0:
        raise HTTPException(400, "Upload video first")
    job = jobs.create("reframe", pid)
    return jobs.submit(job, lambda ctx: reframe_project(store, pid, body.aspect, body.name, ctx, body.focus))


@app.post("/api/projects/{pid}/export")
def export(pid: str, body: ExportBody):
    project = require_project(pid)
    if not body.formats or project.duration <= 0:
        raise HTTPException(400, "Choose export formats and a non-empty project")
    job = jobs.create("export", pid)
    return jobs.submit(job, lambda ctx: export_project(store, pid, body, ctx))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/jobs")
def list_jobs(projectId: str | None = None):
    return jobs.list(projectId)


app.mount("/files/projects", StaticFiles(directory=settings.projects_dir), name="project-files")
# Build the web app to serve a standalone local deployment at :8787.
if settings.web_dist.is_dir():
    app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")
