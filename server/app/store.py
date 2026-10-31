"""Project storage: data/projects/<id>/project.json plus media/ analysis/ gen/ export/."""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

from .models import Project

SUBDIRS = ("media", "analysis", "gen", "export")


class ProjectNotFound(KeyError):
    pass


def write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    # -- paths -------------------------------------------------------------------
    def project_dir(self, pid: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", pid):
            raise ValueError("Invalid project id")
        return self.root / pid

    def project_file(self, pid: str) -> Path:
        return self.project_dir(pid) / "project.json"

    def lock(self, pid: str) -> threading.RLock:
        with self._locks_guard:
            lk = self._locks.get(pid)
            if lk is None:
                lk = self._locks[pid] = threading.RLock()
            return lk

    # -- CRUD ------------------------------------------------------------------------
    def create(self, name: str) -> Project:
        pid = str(uuid.uuid4())
        project = Project(id=pid, name=name or "Untitled")
        pdir = self.project_dir(pid)
        for sub in SUBDIRS:
            (pdir / sub).mkdir(parents=True, exist_ok=True)
        self.save(project)
        return project

    def exists(self, pid: str) -> bool:
        return self.project_file(pid).is_file()

    def load(self, pid: str) -> Project:
        path = self.project_file(pid)
        if not path.is_file():
            raise ProjectNotFound(pid)
        with open(path, encoding="utf-8") as fh:
            return Project.model_validate(json.load(fh))

    def save(self, project: Project) -> Project:
        with self.lock(project.id):
            for sub in SUBDIRS:
                (self.project_dir(project.id) / sub).mkdir(parents=True, exist_ok=True)
            write_json_atomic(self.project_file(project.id), project.model_dump(mode="json"))
        return project

    def update(self, pid: str, fn: Callable[[Project], None]) -> Project:
        """Reload → mutate → save under the project lock (safe from worker threads)."""
        with self.lock(pid):
            project = self.load(pid)
            fn(project)
            return self.save(project)

    def delete(self, pid: str) -> None:
        import shutil

        with self.lock(pid):
            pdir = self.project_dir(pid)
            if not pdir.is_dir():
                raise ProjectNotFound(pid)
            shutil.rmtree(pdir)

    def list(self) -> list[Project]:
        items: list[tuple[float, Project]] = []
        for pf in self.root.glob("*/project.json"):
            try:
                with open(pf, encoding="utf-8") as fh:
                    items.append((pf.stat().st_mtime, Project.model_validate(json.load(fh))))
            except Exception:  # corrupt project — skip rather than break the list
                continue
        items.sort(key=lambda t: t[0], reverse=True)
        return [p for _, p in items]
