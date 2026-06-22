"""Healthcheck helpers.

Writes a small ``last_run.json`` file inside the output folder that Docker
can ping to determine container health. Also exposes ``is_recent`` so the
web UI can show freshness of the last scrape.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional


def write_last_run(folder: str, *, status: str, pages: int, files: int,
                   duration_seconds: float, error: Optional[str] = None) -> str:
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "last_run.json")
    payload = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "pages_crawled": pages,
        "files_downloaded": files,
        "duration_seconds": round(duration_seconds, 3),
        "error": error or "",
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


def read_last_run(folder: str) -> dict:
    path = os.path.join(folder, "last_run.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def is_healthy(folder: str, *, max_age_minutes: int = 60 * 26) -> bool:
    """A run is "healthy" if it succeeded within the last ``max_age_minutes``."""
    info = read_last_run(folder)
    if not info:
        return False
    if info.get("status") != "ok":
        return False
    try:
        last = datetime.fromisoformat(info["last_run"])
    except (KeyError, ValueError):
        return False
    age = (datetime.now(timezone.utc) - last).total_seconds() / 60.0
    return age <= max_age_minutes
