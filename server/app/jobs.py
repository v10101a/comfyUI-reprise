"""Job registry: in-memory + data/jobs/<id>.json, background execution in per-lane worker threads.

Lanes: "comfy" (words / matte / inworld — ComfyUI is serial anyway) and "export"
(Playwright + ffmpeg), one worker thread each so a long matte never blocks an export.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Job, JobKind
from .store import write_json_atomic

log = logging.getLogger("typeset.jobs")

LANES = {"words": "comfy", "matte": "comfy", "inworld": "comfy", "export": "export",
         "surface": "cpu", "reframe": "cpu", "occupancy": "cpu", "beats": "cpu"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class JobContext:
    """Handed to job functions: progress reporting + a per-job log."""

    def __init__(self, manager: "JobManager", job: Job) -> None:
        self.manager = manager
        self.job = job
        self._last_persist = 0.0

    @property
    def id(self) -> str:
        return self.job.id

    def progress(self, value: float | None = None, message: str | None = None) -> None:
        if value is not None:
            self.job.progress = max(0.0, min(1.0, float(value)))
        if message is not None:
            self.job.message = message
            log.info("[job %s %s] %s", self.job.id[:8], self.job.kind, message)
        self.job.updatedAt = _now()
        now = time.monotonic()
        if now - self._last_persist > 0.25 or message is not None:
            self._last_persist = now
            self.manager._persist(self.job)

    def set_result(self, result: Any) -> None:
        self.job.result = result


class JobManager:
    def __init__(self, jobs_dir: Path) -> None:
        self.jobs_dir = jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._lanes: dict[str, ThreadPoolExecutor] = {
            "comfy": ThreadPoolExecutor(max_workers=1, thread_name_prefix="typeset-comfy"),
            "export": ThreadPoolExecutor(max_workers=1, thread_name_prefix="typeset-export"),
            # OpenCV analysis (surface tracking, reframe, occupancy) never waits behind a model job.
            "cpu": ThreadPoolExecutor(max_workers=1, thread_name_prefix="typeset-cpu"),
            # Remote MiniMax shots wait minutes on the 4090; keep local words/matte flowing meanwhile.
            "remote": ThreadPoolExecutor(max_workers=1, thread_name_prefix="typeset-remote"),
        }
        self._load()

    # -- persistence ----------------------------------------------------------------
    def _load(self) -> None:
        for jf in sorted(self.jobs_dir.glob("*.json")):
            try:
                job = Job.model_validate(json.loads(jf.read_text(encoding="utf-8")))
            except Exception:
                continue
            if job.status in ("queued", "running"):
                job.status = "failed"
                job.message = "Server restarted while the job was in progress."
                job.updatedAt = _now()
                self._persist(job)
            self._jobs[job.id] = job

    def _persist(self, job: Job) -> None:
        try:
            write_json_atomic(self.jobs_dir / f"{job.id}.json", job.model_dump(mode="json"))
        except Exception:
            log.exception("failed to persist job %s", job.id)

    # -- API -------------------------------------------------------------------------
    def create(self, kind: JobKind, project_id: str, message: str = "queued") -> Job:
        job = Job(id=str(uuid.uuid4()), kind=kind, status="queued", progress=0.0, message=message,
                  projectId=project_id, createdAt=_now(), updatedAt=_now())
        with self._lock:
            self._jobs[job.id] = job
        self._persist(job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, project_id: str | None = None) -> list[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        if project_id:
            jobs = [j for j in jobs if j.projectId == project_id]
        jobs.sort(key=lambda j: j.createdAt or "", reverse=True)
        return jobs

    def submit(self, job: Job, fn: Callable[[JobContext], Any], lane: str | None = None) -> Job:
        lane = self._lanes[lane or LANES.get(job.kind, "comfy")]
        lane.submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: Callable[[JobContext], Any]) -> None:
        ctx = JobContext(self, job)
        job.status = "running"
        job.updatedAt = _now()
        if not job.message or job.message == "queued":
            job.message = "running"
        self._persist(job)
        t0 = time.monotonic()
        try:
            result = fn(ctx)
            if result is not None:
                job.result = result
            if isinstance(job.result, dict):
                job.result.setdefault("elapsedSeconds", round(time.monotonic() - t0, 2))
            job.status = "done"
            job.progress = 1.0
            if job.message in (None, "running") or (job.message or "").startswith("running"):
                job.message = "done"
            log.info("[job %s %s] done in %.1fs", job.id[:8], job.kind, time.monotonic() - t0)
        except Exception as exc:  # noqa: BLE001 — surface everything to the client
            job.status = "failed"
            job.message = f"{type(exc).__name__}: {exc}"
            log.error("[job %s %s] failed: %s\n%s", job.id[:8], job.kind, exc, traceback.format_exc())
        job.updatedAt = _now()
        self._persist(job)

    def shutdown(self) -> None:
        for lane in self._lanes.values():
            lane.shutdown(wait=False, cancel_futures=True)
