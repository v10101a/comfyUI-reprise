"""Reprise local API. Run: server/.venv/bin/uvicorn app.main:app --app-dir server --port 8787

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

from . import service, showcase, workflows
from .config import settings
from .models import Project, CreateProjectBody, AnalyzeWordsBody, AnalyzeMatteBody, InworldBody, ExportBody, ReframeBody
from .service import ApiError, store, jobs  # noqa: F401  (tests import store from here)

log = logging.getLogger("typeset")


@asynccontextmanager
async def lifespan(app):
    yield
    service.shutdown()


app = FastAPI(title="Reprise", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type"])


@app.exception_handler(ApiError)
async def api_error(request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.exception_handler(workflows.WorkflowApiError)
async def workflow_error(request, exc: workflows.WorkflowApiError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.get("/api/health")
def health():
    return service.health()


@app.get("/api/looks/saved")
def saved_looks():
    return service.saved_looks()


@app.put("/api/looks/saved")
async def set_saved_looks(request: Request):
    return service.set_saved_looks(await request.json())


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


def _add_layer_flag(raw) -> bool | str:
    v = (str(raw).strip().lower() if raw is not None else "")
    return "top" if v == "top" else v in ("1", "true", "yes", "under-text")


@app.post("/api/projects/{pid}/assets")
async def add_asset(pid: str, request: Request):
    """Asset bin: multipart (file, addLayer?, name?) or JSON {comfy:{filename,subfolder,type}, addLayer?, source?, name?}."""
    from starlette.concurrency import run_in_threadpool
    if request.headers.get("content-type", "").startswith("multipart/"):
        form = await request.form()
        file = form.get("file")
        if file is None or not hasattr(file, "file"):
            raise ApiError(422, "file is required")
        try:
            return await run_in_threadpool(service.add_asset, pid, file.filename or "asset", iter(lambda: file.file.read(1024 * 1024), b""),
                                           None, _add_layer_flag(form.get("addLayer")), form.get("name") or None)
        finally:
            await file.close()
    try:
        data = await request.json()
    except Exception:
        raise ApiError(422, "Expected multipart file or JSON {comfy:{...}}") from None
    return await run_in_threadpool(service.assets_json, pid, data)


@app.post("/api/projects/{pid}/analyze/words")
def words(pid: str, body: AnalyzeWordsBody):
    return service.analyze_words_job(pid, body)


@app.post("/api/projects/{pid}/analyze/matte")
def matte(pid: str, body: AnalyzeMatteBody):
    return service.analyze_matte_job(pid, body)


@app.post("/api/projects/{pid}/analyze/heads")
def heads(pid: str):
    return service.analyze_heads_job(pid)


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


# ---- bring-your-own Comfy workflows (workflows.py) + the project ComfyUI's "add to" targets ----

@app.get("/api/workflows")
def list_workflows(remote: bool | None = None, refresh: bool = False):
    return workflows.list_workflows(remote, refresh)


@app.post("/api/workflows")
def import_workflow(body: dict):
    return workflows.import_workflow(body)


@app.get("/api/workflows/{wid}")
def get_workflow(wid: str, remote: bool | None = None):
    return workflows.get_workflow(wid, remote)


@app.put("/api/workflows/{wid}")
def update_workflow(wid: str, body: dict):
    return workflows.update_workflow(wid, body)


@app.post("/api/workflows/{wid}/delete")
def delete_workflow(wid: str):
    return workflows.delete_workflow(wid)


@app.post("/api/projects/{pid}/workflows/{wid}/run")
def run_workflow(pid: str, wid: str, body: dict):
    return workflows.run_job(service, pid, wid, body)


@app.get("/api/session")
def get_session():
    return workflows.current_project()


@app.put("/api/session")
def set_session(data: dict):
    project = service.require_project(str(data.get("projectId") or ""))
    return workflows.set_current_project(project.id, project.name)


app.mount("/files/projects", StaticFiles(directory=settings.projects_dir), name="project-files")
# Build the web app to serve a standalone local deployment at :8787.
if settings.web_dist.is_dir():
    app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")
