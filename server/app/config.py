"""Settings from environment variables. See docs/server.md for the full list."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # server/app/config.py -> repo root


def _path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    workflows_dir: Path
    comfy_dir: Path
    comfy_base_url: str
    comfy_api_key: str
    comfy_timeout: float
    comfyui_url: str
    web_url: str
    web_dist: Path
    server_url: str
    render_url_template: str
    capture: str
    cors_origins: list[str] = field(default_factory=list)
    remote_comfy_url: str | None = None
    remote_comfy_base_url: str = "http://127.0.0.1:8190"
    remote_comfy_api_key: str = "local"
    ffmpeg: str = "/opt/homebrew/bin/ffmpeg"
    ffprobe: str = "/opt/homebrew/bin/ffprobe"
    render_timeout: float = 120.0
    comfy_mode: str = "sdk"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def comfy_input_dir(self) -> Path:
        return self.comfy_dir / "input"

    @property
    def comfy_output_dir(self) -> Path:
        return self.comfy_dir / "output"


def load_settings() -> Settings:
    base_url = os.environ.get("COMFY_BASE_URL", "http://127.0.0.1:8189")
    # The SDK reads COMFY_BASE_URL itself; pin it so every client in this process agrees.
    os.environ["COMFY_BASE_URL"] = base_url
    origins = os.environ.get("TYPESET_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    s = Settings(
        data_dir=_path("TYPESET_DATA_DIR", REPO_ROOT / "data"),
        workflows_dir=_path("TYPESET_WORKFLOWS_DIR", REPO_ROOT / "workflows"),
        comfy_dir=_path("TYPESET_COMFY_DIR", Path.home() / "ComfyUI"),
        comfy_base_url=base_url,
        comfy_api_key=os.environ.get("COMFY_API_KEY", "local"),
        comfy_timeout=float(os.environ.get("TYPESET_COMFY_TIMEOUT", "1800")),
        comfyui_url=os.environ.get("TYPESET_COMFYUI_URL", "http://127.0.0.1:8188"),
        web_url=os.environ.get("TYPESET_WEB_URL", "http://localhost:5173").rstrip("/"),
        web_dist=_path("TYPESET_WEB_DIST", REPO_ROOT / "apps" / "web" / "dist"),
        server_url=os.environ.get("TYPESET_SERVER_URL", "http://localhost:8787").rstrip("/"),
        render_url_template=os.environ.get(
            "TYPESET_RENDER_URL", "{web}/#/render?project={project}&layer={layer}&server={server}"
        ),
        capture=os.environ.get("TYPESET_CAPTURE", "screenshot"),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        remote_comfy_url=os.environ.get("TYPESET_REMOTE_COMFY_URL", "").strip().rstrip("/") or None,
        remote_comfy_base_url=os.environ.get("TYPESET_REMOTE_COMFY_BASE_URL", "http://127.0.0.1:8190").rstrip("/"),
        remote_comfy_api_key=os.environ.get("TYPESET_REMOTE_COMFY_API_KEY", "local"),
        ffmpeg=os.environ.get("FFMPEG", "/opt/homebrew/bin/ffmpeg"),
        ffprobe=os.environ.get("FFPROBE", "/opt/homebrew/bin/ffprobe"),
        render_timeout=float(os.environ.get("TYPESET_RENDER_TIMEOUT", "120")),
        comfy_mode=os.environ.get("TYPESET_COMFY_MODE", "sdk").strip().lower(),
    )
    for d in (s.projects_dir, s.jobs_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s


settings = load_settings()
