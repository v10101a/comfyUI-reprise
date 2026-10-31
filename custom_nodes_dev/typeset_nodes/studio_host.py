"""Typeset studio inside ComfyUI: http://<comfy>/typeset

Mounts the studio (apps/web/dist) and the Typeset project API on ComfyUI's own aiohttp server, so
nothing else has to run: workflows go straight onto ComfyUI's queue (`TYPESET_COMFY_MODE=direct`),
project files live in the repo's data/ dir (or TYPESET_DATA_DIR).

The API logic is server/app/service.py, imported under the package name `typeset_server` because
ComfyUI already owns a top-level `app` package. Without the repo's server/ dir (a bare node-pack
install) the nodes still load and /typeset is simply not mounted.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("typeset.host")

PREFIX = "/typeset"
REPO = Path(__file__).resolve().parents[2]  # custom_nodes_dev/typeset_nodes -> repo (symlinks resolved)


def _comfy_url() -> str:
    try:
        from comfy.cli_args import args
        host = args.listen.split(",")[0] if args.listen else "127.0.0.1"
        if host in ("0.0.0.0", "::", ""):
            host = "127.0.0.1"
        return f"http://{host}:{args.port}"
    except Exception:
        return "http://127.0.0.1:8188"


def _load_service():
    pkg_dir = REPO / "server" / "app"
    if not (pkg_dir / "service.py").is_file():
        return None
    url = _comfy_url()
    os.environ.setdefault("TYPESET_COMFY_MODE", "direct")
    os.environ.setdefault("TYPESET_COMFYUI_URL", url)
    os.environ.setdefault("TYPESET_WEB_URL", url + PREFIX)
    os.environ.setdefault("TYPESET_SERVER_URL", url + PREFIX)
    try:
        import folder_paths
        os.environ.setdefault("TYPESET_COMFY_DIR", str(Path(folder_paths.base_path)))
    except Exception:
        pass
    if "typeset_server" not in sys.modules:
        spec = importlib.util.spec_from_file_location("typeset_server", pkg_dir / "__init__.py",
                                                      submodule_search_locations=[str(pkg_dir)])
        module = importlib.util.module_from_spec(spec)
        sys.modules["typeset_server"] = module
        spec.loader.exec_module(module)
    import typeset_server.service as service  # noqa: E402
    return service


def _dump(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump(v) for v in value]
    return value


def register(server) -> bool:
    """Add /typeset routes to a ComfyUI PromptServer. Returns False when the studio is unavailable."""
    from aiohttp import web

    try:
        service = _load_service()
    except Exception:
        log.exception("Typeset studio: could not load the project API; nodes still work")
        return False
    if service is None:
        log.info("Typeset studio: server/ not found next to the node pack; /typeset not mounted")
        return False
    from typeset_server.config import settings
    from typeset_server import models

    dist = settings.web_dist
    routes = web.RouteTableDef()

    async def call(fn, *args):
        try:
            result = await asyncio.get_running_loop().run_in_executor(None, fn, *args)
        except service.ApiError as exc:
            return web.json_response({"detail": exc.detail}, status=exc.status)
        return web.json_response(_dump(result))

    async def body(request, model):
        from pydantic import ValidationError
        try:
            raw = await request.json() if request.can_read_body else {}
            return model.model_validate(raw or {}), None
        except (ValidationError, json.JSONDecodeError) as exc:
            return None, web.json_response({"detail": str(exc)}, status=422)

    def job_route(path, fn, model=None):
        async def handler(request):
            args = [request.match_info[k] for k in ("pid", "sid") if k in request.match_info]
            if model is not None:
                parsed, err = await body(request, model)
                if err is not None:
                    return err
                args.append(parsed)
            return await call(fn, *args)
        routes.post(f"{PREFIX}/api/projects/{{pid}}{path}")(handler)

    @routes.get(f"{PREFIX}/api/health")
    async def health(request):
        return await call(lambda: {**service.health(), "host": "comfyui", "capture": "browser"})

    @routes.get(f"{PREFIX}/api/projects")
    async def list_projects(request):
        return await call(service.list_projects)

    @routes.post(f"{PREFIX}/api/projects")
    async def create_project(request):
        parsed, err = await body(request, models.CreateProjectBody)
        return err or await call(service.create_project, parsed)

    @routes.get(f"{PREFIX}/api/projects/{{pid}}")
    async def get_project(request):
        return await call(service.require_project, request.match_info["pid"])

    @routes.put(f"{PREFIX}/api/projects/{{pid}}")
    async def save_project(request):
        parsed, err = await body(request, models.Project)
        return err or await call(service.save_project, request.match_info["pid"], parsed)

    @routes.post(f"{PREFIX}/api/projects/{{pid}}/media")
    async def upload_media(request):
        # Stream the multipart file to a temp spool on disk, then hand chunks to the service.
        import tempfile
        reader = await request.multipart()
        kind, filename, spool = None, "upload", tempfile.SpooledTemporaryFile(max_size=8 * 1024**2)
        try:
            async for part in reader:
                if part.name == "kind":
                    kind = (await part.text()).strip()
                elif part.name == "file":
                    filename = part.filename or filename
                    while chunk := await part.read_chunk(1024 * 1024):
                        spool.write(chunk)
            spool.seek(0)
            if kind is None:
                return web.json_response({"detail": "kind is required"}, status=422)
            return await call(service.upload_media, request.match_info["pid"], filename, kind,
                              iter(lambda: spool.read(1024 * 1024), b""))
        finally:
            spool.close()

    job_route("/analyze/words", service.analyze_words_job, models.AnalyzeWordsBody)
    job_route("/analyze/matte", service.analyze_matte_job, models.AnalyzeMatteBody)
    job_route("/generate/inworld", service.inworld_job, models.InworldBody)
    job_route("/analyze/occupancy", service.occupancy_job)
    job_route("/analyze/beats", service.beats_job)
    job_route("/analyze/flow", service.flow_job)
    job_route("/analyze/voice", service.voice_job)
    job_route("/surfaces/{sid}/track", service.surface_track_job)
    job_route("/reframe", service.reframe_job, models.ReframeBody)
    job_route("/export", service.export_job, models.ExportBody)

    @routes.post(f"{PREFIX}/api/import")
    async def import_output(request):
        """A ComfyUI output/input/temp file (as /view addresses it) becomes a new project's footage or song."""
        import folder_paths
        try:
            ref = await request.json()
            filename, kind = str(ref["filename"]), ref.get("kind") or "video"
        except Exception:
            return web.json_response({"detail": "Expected {filename, subfolder, type, kind}"}, status=422)
        base = Path(folder_paths.get_directory_by_type(ref.get("type") or "output") or "").resolve()
        src = (base / str(ref.get("subfolder") or "") / filename).resolve()
        if not base.is_dir() or not src.is_relative_to(base) or not src.is_file():
            return web.json_response({"detail": f"No such ComfyUI file: {filename}"}, status=404)

        def run():
            project = service.create_project(models.CreateProjectBody(name=ref.get("name") or src.stem))
            with src.open("rb") as fh:
                service.upload_media(project.id, src.name, kind, iter(lambda: fh.read(1024 * 1024), b""))
            return service.require_project(project.id)
        return await call(run)

    @routes.post(f"{PREFIX}/api/projects/{{pid}}/export/frames")
    async def start_frames(request):
        return await call(service.start_frames, request.match_info["pid"])

    @routes.put(f"{PREFIX}/api/projects/{{pid}}/export/frames/{{session}}/{{layer}}/{{index:\\d+}}")
    async def put_frame(request):
        m = request.match_info
        return await call(service.put_frame, m["pid"], m["session"], m["layer"], int(m["index"]), await request.read())

    @routes.get(f"{PREFIX}/api/jobs/{{job_id}}")
    async def get_job(request):
        return await call(service.get_job, request.match_info["job_id"])

    @routes.get(f"{PREFIX}/api/jobs")
    async def list_jobs(request):
        return await call(service.list_jobs, request.query.get("projectId"))

    def static(root: Path, rel: str, index: bool = False):
        root = root.resolve()
        path = (root / rel).resolve() if rel else root
        if not path.is_relative_to(root):
            raise web.HTTPForbidden()
        if path.is_dir() and index:
            path = path / "index.html"
        if not path.is_file():
            raise web.HTTPNotFound()
        resp = web.FileResponse(path)  # Range requests work, so video seeking does too
        if path.name == "index.html":
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    @routes.get(f"{PREFIX}/files/projects/{{rel:.*}}")
    async def project_file(request):
        return static(settings.projects_dir, request.match_info["rel"])

    @routes.get(PREFIX)
    async def studio_root(request):
        raise web.HTTPFound(PREFIX + "/")

    @routes.get(f"{PREFIX}/{{rel:.*}}")
    async def studio(request):
        if not dist.is_dir():
            return web.Response(status=503, text="Typeset studio is not built. Run: cd apps/web && pnpm install && pnpm build")
        return static(dist, request.match_info["rel"], index=True)

    server.app.add_routes(routes)
    log.info("Typeset studio: %s%s/ (projects in %s)", _comfy_url(), PREFIX, settings.projects_dir)
    return True
