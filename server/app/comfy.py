"""Sidecar-driven ComfyUI workflow runner.

Two transports: `direct` posts the API graph to ComfyUI's own /prompt and reads /history (no extra
process; the default when Typeset runs inside ComfyUI), `sdk` goes Comfy SDK → comfy-api-proxy → ComfyUI.
A third host, Comfy Cloud (`cloud=True`), speaks the SDK natively: inputs are uploaded as content-hashed
assets (`asset://<id>` placeholders that `_bind` turns into SDK handles) and the v1 Cloud REST surface
(`/api/object_info`, `/api/queue`, X-API-Key) serves preflight and health.

A workflow is addressed by *name*: `<workflows_dir>/<name>.inputs.json` (SCHEMA §3) names
the API-format graph, the inputs (node/field/kind) and the outputs (node/type). The server
never hardcodes node ids.

Robustness notes (all verified against comfy-api-proxy 0.1.x):
  * Never `client.run()` / `job.wait()`: the proxy can report `expired` for an instant right
    after ComfyUI finishes. We poll and treat `expired` as transient for ~5 s.
  * Outputs are downloaded by node id. The proxy's asset id encodes {filename, subfolder, type},
    so when ComfyUI is on this machine we copy the file straight from ~/ComfyUI/output (fast path)
    and fall back to an HTTP download.
  * A `text` output whose node only emitted plain strings (ComfyUI `ui.text`) is invisible to the
    proxy (it requires `filename` entries). We fall back to ComfyUI's own /history/<job> and write
    the strings to a file so callers always get a path.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import httpx

from .config import settings

log = logging.getLogger("typeset.comfy")

TERMINAL = {"succeeded", "failed", "canceled"}
KINDS = {"comfy_input_path", "string", "int", "float", "bool"}
_MISSING = object()
ProgressFn = Callable[[str, float], None]  # (status, elapsed_seconds)
_SDK_ENV_LOCK = threading.Lock()
ASSET_SCHEME = "asset://"  # Comfy Cloud input placeholder: an uploaded asset id
CLOUD_REGISTRY_TTL = 600.0


class _SkipProxy(Exception):
    pass


class WorkflowError(RuntimeError):
    pass


class WorkflowMissing(WorkflowError):
    pass


class WorkflowInputError(WorkflowError):
    pass


class WorkflowRunError(WorkflowError):
    pass


# ---- sidecars -------------------------------------------------------------------

@dataclass
class SidecarInput:
    node: str
    field: str
    kind: str
    default: Any = _MISSING
    optional: bool = False


@dataclass
class SidecarOutput:
    node: str
    type: str = "image"
    optional: bool = False


@dataclass
class Sidecar:
    name: str
    path: Path
    workflow_path: Path
    description: str = ""
    inputs: dict[str, SidecarInput] = field(default_factory=dict)
    outputs: dict[str, SidecarOutput] = field(default_factory=dict)


def sidecar_path(name: str, workflows_dir: Path | None = None) -> Path:
    p = Path(name)
    if p.suffix == ".json" and p.name.endswith(".inputs.json"):
        return p if p.is_absolute() else (workflows_dir or settings.workflows_dir) / p
    return (workflows_dir or settings.workflows_dir) / f"{name}.inputs.json"


def load_sidecar(name: str, workflows_dir: Path | None = None) -> Sidecar:
    path = sidecar_path(name, workflows_dir)
    if not path.is_file():
        raise WorkflowMissing(
            f"Workflow sidecar not found: {path} — the '{Path(name).name.replace('.inputs.json', '')}' workflow has not been delivered yet."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"Sidecar {path} is not valid JSON: {exc}") from exc
    wf_name = data.get("workflow")
    if not wf_name:
        raise WorkflowError(f"Sidecar {path} has no 'workflow' key")
    wf_path = (path.parent / wf_name) if not os.path.isabs(wf_name) else Path(wf_name)
    if not wf_path.is_file():
        raise WorkflowMissing(f"Workflow file not found: {wf_path} (referenced by {path.name})")

    inputs: dict[str, SidecarInput] = {}
    for key, spec in (data.get("inputs") or {}).items():
        kind = spec.get("kind", "string")
        if kind not in KINDS:
            raise WorkflowError(f"Sidecar {path.name}: input '{key}' has unknown kind '{kind}' (expected one of {sorted(KINDS)})")
        inputs[key] = SidecarInput(
            node=str(spec["node"]), field=str(spec["field"]), kind=kind,
            default=spec.get("default", _MISSING), optional=bool(spec.get("optional", False)),
        )
    outputs: dict[str, SidecarOutput] = {}
    for key, spec in (data.get("outputs") or {}).items():
        outputs[key] = SidecarOutput(node=str(spec["node"]), type=str(spec.get("type", "image")), optional=bool(spec.get("optional", False)))
    return Sidecar(name=Path(name).name.replace(".inputs.json", ""), path=path, workflow_path=wf_path,
                   description=data.get("description", ""), inputs=inputs, outputs=outputs)


def remote_input_path(value: Any) -> str:
    rel = str(value).replace("\\", "/")
    path = PurePosixPath(rel)
    if path.is_absolute() or ".." in path.parts or not path.parts or ":" in rel:
        raise WorkflowInputError("Remote input must be a relative ComfyUI input path")
    return str(path)


def coerce(kind: str, value: Any, name: str, *, remote: bool = False) -> Any:
    try:
        if kind == "int":
            return int(round(float(value))) if not isinstance(value, bool) else int(value)
        if kind == "float":
            return float(value)
        if kind == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if kind == "comfy_input_path":
            if remote:
                return remote_input_path(value)
            rel = str(value).replace("\\", "/")
            candidate = (settings.comfy_input_dir / rel).resolve()
            if Path(rel).is_absolute() or not candidate.is_relative_to(settings.comfy_input_dir.resolve()):
                raise WorkflowInputError(f"input {name}: path must stay inside ComfyUI input")
            if not (settings.comfy_input_dir / rel).exists():
                raise WorkflowInputError(f"input '{name}': file not found in ComfyUI input dir: {settings.comfy_input_dir / rel}")
            return rel
        return str(value)
    except (TypeError, ValueError) as exc:
        raise WorkflowInputError(f"input '{name}': cannot coerce {value!r} to {kind}: {exc}") from exc


# ---- asset id decoding (proxy fast path) ----------------------------------------

def decode_asset_id(asset_id: str) -> dict[str, str] | None:
    """comfy-api-proxy mints output ids as base64url(JSON{j,f,s,t}).<hmac>. Decode the payload."""
    try:
        payload = asset_id.split(".", 1)[0]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        if isinstance(data, dict) and "f" in data:
            return {"job": data.get("j", ""), "filename": data["f"], "subfolder": data.get("s", ""), "type": data.get("t", "output")}
    except Exception:
        return None
    return None


def local_output_path(ref: dict[str, str]) -> Path | None:
    base = {"output": settings.comfy_output_dir, "temp": settings.comfy_dir / "temp", "input": settings.comfy_input_dir}.get(ref.get("type", "output"))
    if base is None:
        return None
    p = (base / ref.get("subfolder", "") / ref["filename"]).resolve()
    try:
        p.relative_to(base.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


# ---- runner ---------------------------------------------------------------------

@dataclass
class RunResult:
    name: str
    job_id: str
    status: str
    outputs: dict[str, list[Path]]
    timing: dict[str, float]
    raw_outputs: list[dict[str, Any]] = field(default_factory=list)

    def first(self, key: str) -> Path | None:
        files = self.outputs.get(key) or []
        return files[0] if files else None


def read_text_output(paths: list[Path]) -> str:
    if not paths:
        raise WorkflowRunError("text output has no files")
    return Path(paths[0]).read_text(encoding="utf-8")


def read_json_output(paths: list[Path]) -> Any:
    text = read_text_output(paths).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorkflowRunError(f"text output {paths[0].name} is not valid JSON: {exc}") from exc


class ComfyRunner:
    def __init__(self, *, base_url: str | None = None, comfyui_url: str | None = None,
                 api_key: str | None = None, remote: bool = False, direct: bool | None = None,
                 cloud: bool = False) -> None:
        self._client = None
        self.cloud = cloud
        # Cloud only exists behind the SDK (asset uploads, signed downloads); `direct` has no /prompt to post to.
        self.direct = False if cloud else (settings.comfy_mode == "direct" if direct is None else direct)
        self._client_lock = threading.Lock()
        self.base_url = (base_url or settings.comfy_base_url).rstrip("/")
        self.comfyui_url = (comfyui_url or settings.comfyui_url).rstrip("/")
        self.api_key = api_key or settings.comfy_api_key
        self.remote = remote or cloud
        self._assets: dict[str, Any] = {}  # Cloud: asset id -> SDK handle (hash + path hints for the upload)
        self._registry: tuple[float, dict] | None = None

    @property
    def api_headers(self) -> dict[str, str] | None:
        """Auth for raw REST calls to the generation host (only Comfy Cloud needs any)."""
        return {"X-API-Key": self.api_key} if self.cloud else None

    def client(self):
        with self._client_lock:
            if self._client is None:
                from comfy_sdk import Comfy

                # This SDK version takes its URL from the environment only at construction.
                # Serialize construction and restore it so local/remote clients cannot bleed.
                with _SDK_ENV_LOCK:
                    previous = os.environ.get("COMFY_BASE_URL")
                    try:
                        os.environ["COMFY_BASE_URL"] = self.base_url
                        self._client = Comfy(api_key=self.api_key, timeout=120)
                    finally:
                        if previous is None:
                            os.environ.pop("COMFY_BASE_URL", None)
                        else:
                            os.environ["COMFY_BASE_URL"] = previous
            return self._client

    def reset_client(self) -> None:
        with self._client_lock:
            try:
                if self._client is not None:
                    self._client.close()
            finally:
                self._client = None

    # -- health --------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        out: dict[str, Any] = {"proxy": False, "comfyui": False, "proxyUrl": self.base_url, "comfyuiUrl": self.comfyui_url,
                               "transport": "direct" if self.direct else "sdk", "host": "cloud" if self.cloud else "comfyui"}
        if self.cloud:
            # Cloud has no /api/v2/health route. Its authenticated queue endpoint
            # checks account access without submitting a job or spending credits.
            try:
                r = httpx.get(f"{self.comfyui_url}/queue", headers=self.api_headers, timeout=8)
                r.raise_for_status()
                q = r.json()
                out.update(proxy=True, comfyui=True, comfyuiVersion="cloud",
                           queue={"running": len(q.get("queue_running") or []),
                                  "pending": len(q.get("queue_pending") or [])})
            except httpx.HTTPStatusError as exc:
                out["comfyuiError"] = f"Comfy Cloud account check failed (HTTP {exc.response.status_code})"
            except Exception as exc:
                out["comfyuiError"] = str(exc)
            return out
        try:
            if self.direct:
                raise _SkipProxy
            r = httpx.get(f"{self.base_url}/api/v2/health", timeout=3)
            out["proxy"] = r.status_code == 200
        except _SkipProxy:
            pass
        except Exception as exc:
            out["proxyError"] = str(exc)
        try:
            r = httpx.get(f"{self.comfyui_url}/system_stats", timeout=3)
            out["comfyui"] = r.status_code == 200
            if out["comfyui"]:
                out["comfyuiVersion"] = r.json().get("system", {}).get("comfyui_version")
        except Exception as exc:
            out["comfyuiError"] = str(exc)
        return out

    def stage_image(self, src: Path, project_id: str, *parts: str) -> str:
        if self.cloud:
            return self.stage_asset(src)
        if not self.remote:
            from .media import stage_to_comfy_input
            return stage_to_comfy_input(src, project_id, *parts)
        rel = remote_input_path("/".join(["typeset", project_id, *(parts or (src.name,))]))
        path = PurePosixPath(rel)
        with src.open("rb") as file:
            response = httpx.post(f"{self.comfyui_url}/upload/image",
                data={"type": "input", "subfolder": str(path.parent), "overwrite": "false"},
                files={"image": (path.name, file, "image/png")}, timeout=120)
        response.raise_for_status()
        uploaded = response.json()
        if uploaded.get("type", "input") != "input":
            raise WorkflowRunError("Remote upload did not return an input file")
        return remote_input_path("/".join(filter(None, [uploaded.get("subfolder", ""), uploaded["name"]])))

    def stage_asset(self, src: Path) -> str:
        """Upload a file to Comfy Cloud (content-hashed; a repeat upload is free) and return its asset:// placeholder.

        The placeholder is a plain string so job provenance stays JSON; `_bind` swaps it for the SDK handle."""
        src = Path(src)
        if not src.is_file():
            raise WorkflowInputError(f"Cannot upload {src}: not a file")
        asset = self.client().assets.from_file(src)
        try:
            asset_id = asset.commit()
        except Exception as exc:
            raise WorkflowRunError(f"Comfy Cloud upload of {src.name} failed: {type(exc).__name__}: {exc}") from exc
        self._assets[asset_id] = asset
        log.info("cloud asset %s <- %s (%s)", asset_id, src.name, "new" if asset.created_new else "dedup")
        return f"{ASSET_SCHEME}{asset_id}"

    def _cloud_input(self, value: Any, name: str) -> Any:
        """A `comfy_input_path` on Comfy Cloud: an asset:// placeholder (preferred) or a local file to upload now."""
        text = str(value)
        if text.startswith(ASSET_SCHEME):
            asset_id = text[len(ASSET_SCHEME):]
            handle = self._assets.get(asset_id)
            if handle is not None:
                return handle
            from comfy_sdk._core import asset_reference  # id alone is authoritative; hints are optional
            return asset_reference(asset_id)
        path = Path(text)
        if path.is_file():
            return self._assets[self.stage_asset(path)[len(ASSET_SCHEME):]]
        raise WorkflowInputError(f"input '{name}': Comfy Cloud needs an uploaded asset (asset://id) or a local file, got {text!r}")

    def object_info(self, *, force: bool = False, timeout: float = 30) -> dict:
        """Node registry of the generation host. Cloud's lists 900+ models, so it is cached for a while."""
        if self.cloud and not force and self._registry and time.monotonic() - self._registry[0] < CLOUD_REGISTRY_TTL:
            return self._registry[1]
        r = httpx.get(f"{self.comfyui_url}/object_info", headers=self.api_headers, timeout=timeout)
        if self.cloud and r.status_code in (401, 403):
            raise WorkflowRunError(f"Comfy Cloud rejected the API key (HTTP {r.status_code}); check TYPESET_CLOUD_API_KEY and that the plan includes API access")
        r.raise_for_status()
        registry = r.json()
        if self.cloud:
            self._registry = (time.monotonic(), registry)
        return registry

    def preflight(self, name: str, workflows_dir: Path | None = None) -> None:
        sidecar = load_sidecar(name, workflows_dir)
        self.preflight_graph(json.loads(sidecar.workflow_path.read_text()))

    def preflight_graph(self, graph: dict) -> None:
        """Check the chosen remote host before uploading or submitting expensive work."""
        try:
            if self.cloud:
                registry = self.object_info()
            else:
                proxy = None if self.direct else httpx.get(f"{self.base_url}/api/v2/health", timeout=5)
                if proxy is not None:
                    proxy.raise_for_status()
                upstream = self.comfyui_url if proxy is None else str(proxy.json().get("upstream", "")).rstrip("/")
                if upstream != self.comfyui_url:
                    raise WorkflowRunError(f"Remote proxy upstream is {upstream!r}; expected {self.comfyui_url}. Start a separate proxy on 8190; do not repoint the local 8189 proxy.")
                response = httpx.get(f"{self.comfyui_url}/object_info", timeout=30)
                response.raise_for_status()
                registry = response.json()
        except WorkflowRunError:
            raise
        except Exception as exc:
            if self.cloud:
                raise WorkflowRunError(f"Cannot reach Comfy Cloud at {self.comfyui_url}: {exc}") from exc
            raise WorkflowRunError(f"Cannot reach remote ComfyUI/proxy. Start the separate remote proxy at {self.base_url} targeting {self.comfyui_url}: {exc}") from exc
        missing = []
        model_fields = {"ckpt_name", "unet_name", "clip_name", "vae_name", "lora_name", "model_name"}
        for node in graph.values():
            kind = node["class_type"]
            if kind not in registry:
                missing.append(f"node {kind}")
                continue
            schema = registry[kind].get("input", {})
            specs = {**schema.get("required", {}), **schema.get("optional", {})}
            for name, value in node.get("inputs", {}).items():
                spec = specs.get(name)
                if name in model_fields and isinstance(value, str) and spec and isinstance(spec[0], list) and value not in spec[0]:
                    missing.append(f"{kind}.{name}={value}")
        if missing:
            if self.cloud:
                raise WorkflowRunError("Comfy Cloud does not host these (custom nodes cannot be installed there; pick a hosted model or node): " + "; ".join(dict.fromkeys(missing)))
            raise WorkflowRunError(f"Remote ComfyUI is not ready: install missing nodes/weights on {self.comfyui_url}: " + "; ".join(dict.fromkeys(missing)))

    # -- main entry ----------------------------------------------------------------
    def run(
        self,
        name: str,
        inputs: dict[str, Any],
        out_dir: Path,
        *,
        progress: ProgressFn | None = None,
        timeout: float | None = None,
        poll_interval: float = 0.5,
        workflows_dir: Path | None = None,
    ) -> RunResult:
        sidecar = load_sidecar(name, workflows_dir)
        timeout = timeout or settings.comfy_timeout
        if self.direct:
            return self._run_direct(sidecar, inputs, out_dir, progress=progress, timeout=timeout, poll_interval=poll_interval)
        client = self.client()
        wf = client.workflows.from_file(str(sidecar.workflow_path))
        bound = self._bind(sidecar, inputs, wf.json, wf.set_input)
        if self.remote:
            self.preflight_graph(wf.json)

        # submit + poll with grace
        t0 = time.monotonic()
        try:
            job = client.submit(wf)
        except Exception as exc:
            raise WorkflowRunError(f"workflow '{sidecar.name}': submit failed: {type(exc).__name__}: {exc}") from exc
        t_submitted = time.monotonic()
        log.info("workflow %s: submitted job %s", sidecar.name, job.id)

        expired_strikes = 0
        last = None
        status = job.status
        while True:
            elapsed = time.monotonic() - t0
            if elapsed > timeout:
                try:
                    job.cancel()
                except Exception:
                    pass
                raise WorkflowRunError(f"workflow '{sidecar.name}': job {job.id} timed out after {timeout:.0f}s (status={status})")
            try:
                job.refresh()
                status = job.status
            except Exception as exc:  # transient proxy hiccup
                log.warning("workflow %s: refresh failed (%s); retrying", sidecar.name, exc)
                time.sleep(poll_interval * 2)
                continue
            if status != last:
                log.info("workflow %s: %6.1fs %s", sidecar.name, elapsed, status)
                last = status
            if progress:
                progress(status, elapsed)
            if status in TERMINAL:
                break
            if status == "expired":
                expired_strikes += 1
                if expired_strikes >= 10:
                    break
            else:
                expired_strikes = 0
            time.sleep(poll_interval)
        t_done = time.monotonic()

        if status != "succeeded":
            err = job.error
            detail = ""
            if isinstance(err, dict):
                detail = f" — {err.get('message') or ''} (node {err.get('node_id')} {err.get('class_type') or ''})".rstrip()
            elif err:
                detail = f" — {err}"
            raise WorkflowRunError(f"workflow '{sidecar.name}': job {job.id} ended '{status}'{detail}")

        # collect outputs
        out_dir.mkdir(parents=True, exist_ok=True)
        results: dict[str, list[Path]] = {}
        raw = [{"node_id": o.node_id, "name": o.name, "type": o.type, "id": o.id} for o in job.outputs]
        for key, spec in sidecar.outputs.items():
            outs = job.get_outputs(spec.node)
            files: list[Path] = []
            dest_dir = out_dir / key
            if outs:
                dest_dir.mkdir(parents=True, exist_ok=True)
                for o in outs:
                    files.append(self._fetch_output(o, dest_dir))
            elif spec.type == "text":
                text = self._history_text(job.id, spec.node)
                if text is not None:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    ext = ".json" if _looks_like_json(text) else ".txt"
                    p = dest_dir / f"{key}{ext}"
                    p.write_text(text, encoding="utf-8")
                    files.append(p)
            if not files and not spec.optional:
                produced = sorted({o.node_id for o in job.outputs})
                raise WorkflowRunError(
                    f"workflow '{sidecar.name}': no '{spec.type}' output on node {spec.node} ('{key}'). "
                    f"Nodes that produced outputs: {produced or 'none'}. The node must save a file and return "
                    f"ui.images/gifs/audio/text/files entries with filename/subfolder/type."
                )
            files.sort(key=lambda p: p.name)
            results[key] = files
        t_fetched = time.monotonic()
        timing = {
            "submit": round(t_submitted - t0, 3),
            "run": round(t_done - t_submitted, 3),
            "download": round(t_fetched - t_done, 3),
            "total": round(t_fetched - t0, 3),
        }
        log.info("workflow %s: done job %s timing=%s files=%s", sidecar.name, job.id, timing, {k: len(v) for k, v in results.items()})
        return RunResult(name=sidecar.name, job_id=job.id, status=status, outputs=results, timing=timing, raw_outputs=raw)

    def _bind(self, sidecar: Sidecar, inputs: dict[str, Any], graph: dict, set_input: Callable[[str, str, Any], None]) -> dict[str, Any]:
        """Bind named inputs onto graph nodes by sidecar kind."""
        bound: dict[str, Any] = {}
        unknown = [k for k in inputs if k not in sidecar.inputs]
        if unknown:
            log.warning("workflow %s: ignoring inputs not in sidecar: %s", sidecar.name, unknown)
        for key, spec in sidecar.inputs.items():
            value = inputs.get(key, _MISSING)
            if value is _MISSING or value is None:
                if spec.default is not _MISSING:
                    value = spec.default
                elif spec.optional:
                    continue
                else:
                    raise WorkflowInputError(f"workflow '{sidecar.name}': required input '{key}' (node {spec.node}.{spec.field}) was not provided")
            if self.cloud and spec.kind == "comfy_input_path":
                value = self._cloud_input(value, key)
            else:
                value = coerce(spec.kind, value, key, remote=self.remote)
            node = graph.get(spec.node)
            if node is None:
                raise WorkflowError(f"workflow '{sidecar.name}': sidecar input '{key}' points at node {spec.node} which is not in {sidecar.workflow_path.name}")
            set_input(spec.node, spec.field, value)
            bound[key] = value
        log.info("workflow %s: inputs %s", sidecar.name, {k: (v if not isinstance(v, str) or len(v) < 80 else v[:77] + "...") for k, v in bound.items()})
        return bound


    def _run_direct(self, sidecar: Sidecar, inputs: dict[str, Any], out_dir: Path, *, progress: ProgressFn | None,
                    timeout: float, poll_interval: float) -> RunResult:
        """POST /prompt to ComfyUI itself, poll /history, collect files the output nodes reported."""
        graph = json.loads(sidecar.workflow_path.read_text(encoding="utf-8"))
        def set_input(node: str, field: str, value: Any) -> None:
            graph[node]["inputs"][field] = value
        self._bind(sidecar, inputs, graph, set_input)
        if self.remote:
            self.preflight_graph(graph)
        t0 = time.monotonic()
        try:
            r = httpx.post(f"{self.comfyui_url}/prompt", json={"prompt": graph, "client_id": f"typeset-{uuid.uuid4().hex[:8]}"}, timeout=60)
        except Exception as exc:
            raise WorkflowRunError(f"workflow '{sidecar.name}': submit failed: {type(exc).__name__}: {exc}") from exc
        if r.status_code != 200:
            try:
                detail = r.json()
                err = detail.get("error") or {}
                msg = err.get("message", "") + (f" — {err.get('details')}" if err.get("details") else "")
                for nid, ne in (detail.get("node_errors") or {}).items():
                    msg += f"; node {nid} {ne.get('class_type', '')}: " + ", ".join(e.get("details") or e.get("message", "") for e in ne.get("errors", []))
            except Exception:
                msg = r.text[:400]
            raise WorkflowRunError(f"workflow '{sidecar.name}': ComfyUI rejected the graph: {msg}")
        job_id = r.json()["prompt_id"]
        t_submitted = time.monotonic()
        log.info("workflow %s: queued prompt %s", sidecar.name, job_id)
        entry: dict[str, Any] = {}
        while True:
            elapsed = time.monotonic() - t0
            if elapsed > timeout:
                try:
                    httpx.post(f"{self.comfyui_url}/queue", json={"delete": [job_id]}, timeout=5)
                    httpx.post(f"{self.comfyui_url}/interrupt", json={"prompt_id": job_id}, timeout=5)
                except Exception:
                    pass
                raise WorkflowRunError(f"workflow '{sidecar.name}': prompt {job_id} timed out after {timeout:.0f}s")
            try:
                h = httpx.get(f"{self.comfyui_url}/history/{job_id}", timeout=10)
                entry = (h.json() or {}).get(job_id) or {} if h.status_code == 200 else {}
            except Exception as exc:
                log.warning("workflow %s: history poll failed (%s); retrying", sidecar.name, exc)
                entry = {}
            status = entry.get("status") or {}
            if status.get("completed") or status.get("status_str") == "error":
                break
            if progress:
                progress("running" if entry else "queued", elapsed)
            time.sleep(poll_interval)
        t_done = time.monotonic()
        if status.get("status_str") != "success":
            detail = ""
            for kind, data in status.get("messages") or []:
                if kind == "execution_error":
                    detail = f" — {data.get('exception_message', '').strip()} (node {data.get('node_id')} {data.get('node_type', '')})"
            raise WorkflowRunError(f"workflow '{sidecar.name}': prompt {job_id} failed{detail}")
        if progress:
            progress("succeeded", t_done - t0)
        node_outputs = entry.get("outputs") or {}
        out_dir.mkdir(parents=True, exist_ok=True)
        results: dict[str, list[Path]] = {}
        for key, spec in sidecar.outputs.items():
            node_out = node_outputs.get(spec.node) or {}
            files: list[Path] = []
            dest_dir = out_dir / key
            refs = [it for items in node_out.values() if isinstance(items, list) for it in items if isinstance(it, dict) and "filename" in it]
            for ref in refs:
                dest_dir.mkdir(parents=True, exist_ok=True)
                files.append(self._fetch_ref(ref, dest_dir))
            if not files and spec.type == "text":
                text = self._text_of(node_out)
                if text is not None:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    p = dest_dir / f"{key}{'.json' if _looks_like_json(text) else '.txt'}"
                    p.write_text(text, encoding="utf-8")
                    files.append(p)
            if not files and not spec.optional:
                raise WorkflowRunError(f"workflow '{sidecar.name}': no '{spec.type}' output on node {spec.node} ('{key}'). "
                                       f"Nodes that produced outputs: {sorted(node_outputs) or 'none'}.")
            files.sort(key=lambda p: p.name)
            results[key] = files
        t_fetched = time.monotonic()
        timing = {"submit": round(t_submitted - t0, 3), "run": round(t_done - t_submitted, 3),
                  "download": round(t_fetched - t_done, 3), "total": round(t_fetched - t0, 3)}
        log.info("workflow %s: done prompt %s timing=%s files=%s", sidecar.name, job_id, timing, {k: len(v) for k, v in results.items()})
        raw = [{"node_id": n, "keys": sorted(o)} for n, o in node_outputs.items()]
        return RunResult(name=sidecar.name, job_id=job_id, status="succeeded", outputs=results, timing=timing, raw_outputs=raw)

    def _fetch_ref(self, ref: dict[str, Any], dest_dir: Path) -> Path:
        ref = {"filename": ref["filename"], "subfolder": ref.get("subfolder", ""), "type": ref.get("type", "output")}
        dest = dest_dir / Path(ref["filename"]).name
        src = None if self.remote else local_output_path(ref)
        if dest.exists():
            dest.unlink()
        if src is not None:
            try:
                os.link(src, dest)
            except OSError:
                shutil.copy2(src, dest)
            return dest
        r = httpx.get(f"{self.comfyui_url}/view", params=ref, timeout=120)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return dest

    @staticmethod
    def _text_of(node_out: dict[str, Any]) -> str | None:
        for key in ("text", "string", "strings", "json", "result"):
            items = node_out.get(key)
            if isinstance(items, list) and items and all(isinstance(i, str) for i in items):
                return "\n".join(items) if len(items) > 1 else items[0]
        return None

    # -- helpers -------------------------------------------------------------------
    def _fetch_output(self, output, dest_dir: Path) -> Path:
        dest = dest_dir / Path(output.name).name
        ref = decode_asset_id(output.id)
        src = local_output_path(ref) if ref and not self.remote else None
        if src is not None:
            try:
                if dest.exists():
                    dest.unlink()
                try:
                    os.link(src, dest)
                except OSError:
                    shutil.copy2(src, dest)
                return dest
            except OSError as exc:
                log.warning("local copy of %s failed (%s); downloading instead", src, exc)
        output.to_file(dest)
        return dest

    def _history_text(self, job_id: str, node: str) -> str | None:
        """Fallback for text outputs the proxy cannot see (plain-string ui.text entries)."""
        if self.cloud:
            return None  # the Cloud API has no /history; text outputs must be saved as files there
        try:
            r = httpx.get(f"{self.comfyui_url}/history/{job_id}", timeout=10)
            if r.status_code != 200:
                return None
            entry = r.json().get(job_id) or {}
            node_out = (entry.get("outputs") or {}).get(node) or {}
        except Exception as exc:
            log.warning("history fallback failed: %s", exc)
            return None
        for key in ("text", "string", "strings", "json", "result"):
            items = node_out.get(key)
            if isinstance(items, list) and items and all(isinstance(i, str) for i in items):
                return "\n".join(items) if len(items) > 1 else items[0]
        # some nodes save a file but under a non-standard key — try to read it from disk
        for items in node_out.values():
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict) and "filename" in it:
                        if self.remote:
                            response = httpx.get(f"{self.comfyui_url}/view", params={"filename": it["filename"], "subfolder": it.get("subfolder", ""), "type": it.get("type", "output")}, timeout=60)
                            response.raise_for_status()
                            return response.text
                        p = local_output_path({"filename": it["filename"], "subfolder": it.get("subfolder", ""), "type": it.get("type", "output")})
                        if p is not None:
                            return p.read_text(encoding="utf-8")
        return None


def _looks_like_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except Exception:
        return False


runner = ComfyRunner()
if settings.cloud_api_key:
    remote_runner: ComfyRunner | None = ComfyRunner(base_url=settings.cloud_url, comfyui_url=f"{settings.cloud_url}/api",
                                                    api_key=settings.cloud_api_key, cloud=True)
elif settings.remote_comfy_url:
    remote_runner = ComfyRunner(base_url=settings.remote_comfy_base_url, comfyui_url=settings.remote_comfy_url,
                                api_key=settings.remote_comfy_api_key, remote=True)
else:
    remote_runner = None


def generation_runner() -> ComfyRunner:
    return remote_runner or runner
