"""Typeset local API. Run: server/.venv/bin/uvicorn app.main:app --app-dir server --port 8787

Thin FastAPI adapter over `service.py`; the same API also runs inside ComfyUI at /typeset (see
custom_nodes_dev/typeset_nodes/studio_host.py).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import service, showcase
from .config import settings
from .models import Project, CreateProjectBody, AnalyzeWordsBody, AnalyzeMatteBody, InworldBody, ExportBody, ReframeBody
from .service import ApiError, store, jobs  # noqa: F401  (tests import store from here)

log = logging.getLogger("typeset")


@asynccontextmanager
async def lifespan(app):
    yield
    service.shutdown()


app = FastAPI(title="Typeset", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type"])


@app.exception_handler(ApiError)
async def api_error(request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.get("/api/health")
def health():
    return service.health()


@app.post("/api/projects", response_model=Project)
def create_project(body: CreateProjectBody):
    return service.create_project(body)


@app.get("/api/projects", response_model=list[Project])
def list_projects():
    return service.list_projects()


@app.get("/api/projects/{pid}", response_model=Project)
def get_project(pid: str):
    return service.require_project(pid)


@app.put("/api/projects/{pid}", response_model=Project)
def save_project(pid: str, body: Project):
    return service.save_project(pid, body)


@app.post("/api/projects/{pid}/media")
def upload_media(pid: str, file: UploadFile = File(...), kind: Literal["video", "audio", "reference"] = Form(...)):
    try:
        return service.upload_media(pid, file.filename or "upload", kind, iter(lambda: file.file.read(1024 * 1024), b""))
    finally:
        file.file.close()


@app.post("/api/projects/{pid}/analyze/words")
def words(pid: str, body: AnalyzeWordsBody):
    return service.analyze_words_job(pid, body)


@app.post("/api/projects/{pid}/analyze/matte")
def matte(pid: str, body: AnalyzeMatteBody):
    return service.analyze_matte_job(pid, body)


@app.post("/api/projects/{pid}/generate/inworld")
def inworld(pid: str, body: InworldBody):
    return service.inworld_job(pid, body)


@app.post("/api/projects/{pid}/analyze/occupancy")
def occupancy(pid: str):
    return service.occupancy_job(pid)


@app.post("/api/projects/{pid}/analyze/beats")
def beats(pid: str):
    return service.beats_job(pid)


@app.post("/api/projects/{pid}/analyze/flow")
def flow(pid: str):
    return service.flow_job(pid)


@app.post("/api/projects/{pid}/analyze/voice")
def voice(pid: str):
    return service.voice_job(pid)


@app.post("/api/projects/{pid}/analyze/audio")
def audio(pid: str):
    return service.audio_job(pid)


@app.post("/api/projects/{pid}/surfaces/{sid}/track")
def surface_track(pid: str, sid: str):
    return service.surface_track_job(pid, sid)


@app.post("/api/projects/{pid}/reframe")
def reframe(pid: str, body: ReframeBody):
    return service.reframe_job(pid, body)


@app.post("/api/projects/{pid}/export")
def export(pid: str, body: ExportBody):
    return service.export_job(pid, body)


@app.post("/api/projects/{pid}/export/frames")
def start_frames(pid: str):
    return service.start_frames(pid)


@app.put("/api/projects/{pid}/export/frames/{session}/{layer}/{index}")
async def put_frame(pid: str, session: str, layer: str, index: int, request: Request):
    return service.put_frame(pid, session, layer, index, await request.body())


@app.get("/api/showcase")
def showcase_versions():
    return showcase.versions()


@app.post("/api/projects/{pid}/showcase")
def showcase_refresh(pid: str):
    """Re-render this project's demo-page clip (no-op 404 when the project has no showcase piece)."""
    service.require_project(pid)
    job = showcase.refresh_job(store, jobs, pid)
    if job is None:
        raise ApiError(404, "No showcase piece for this project")
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return service.get_job(job_id)


@app.get("/api/jobs")
def list_jobs(projectId: str | None = None):
    return service.list_jobs(projectId)


app.mount("/files/projects", StaticFiles(directory=settings.projects_dir), name="project-files")
# Build the web app to serve a standalone local deployment at :8787.
if settings.web_dist.is_dir():
    app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")
