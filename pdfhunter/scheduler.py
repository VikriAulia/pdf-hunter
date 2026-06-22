"""Multi-schedule scheduler.

A schedule is ``(name, cron_expression, preset_path)``. The scheduler reads
``PDF_SCRAPER_SCHEDULES`` (JSON list) **or** ``presets/schedules.yaml`` and
runs each preset via :func:`pdfhunter.runner.run_once` using ``croniter``.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

try:
    from croniter import croniter  # type: ignore
except Exception:  # pragma: no cover - optional
    croniter = None  # type: ignore

import yaml  # type: ignore

from .config import Config, from_env, load_preset
from .runner import run_once


SCHEDULES_FILE = os.path.join("presets", "schedules.yaml")


@dataclass
class Schedule:
    name: str
    cron: str
    preset: Optional[str] = None
    enabled: bool = True


def _load_yaml(path: str) -> List[Schedule]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    schedules = []
    for item in data.get("schedules", []):
        if not isinstance(item, dict):
            continue
        schedules.append(Schedule(
            name=item.get("name", item.get("cron", "schedule")),
            cron=item.get("cron", ""),
            preset=item.get("preset"),
            enabled=bool(item.get("enabled", True)),
        ))
    return schedules


def _load_env() -> List[Schedule]:
    raw = os.getenv("PDF_SCRAPER_SCHEDULES", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logging.warning("PDF_SCRAPER_SCHEDULES is not valid JSON, ignoring")
        return []
    out = []
    for item in data:
        if isinstance(item, dict):
            out.append(Schedule(
                name=item.get("name", item.get("cron", "schedule")),
                cron=item.get("cron", ""),
                preset=item.get("preset"),
                enabled=bool(item.get("enabled", True)),
            ))
    return out


def load_schedules(path: str = SCHEDULES_FILE) -> List[Schedule]:
    schedules = _load_env()
    schedules.extend(_load_yaml(path))
    return [s for s in schedules if s.cron]


def _next_run(cron_expr: str, now: float) -> float:
    if croniter is None:  # pragma: no cover
        raise RuntimeError("croniter is not installed; `pip install croniter`")
    return croniter(cron_expr, now).get_next(float)


def run_schedule(schedule: Schedule, base_cfg: Config) -> None:
    """Execute a single schedule, loading its preset if any."""
    cfg = load_preset(schedule.preset) if schedule.preset else base_cfg
    cfg.cron_schedule = schedule.cron
    logging.info("[scheduler] running schedule '%s' (cron=%s, preset=%s)",
                 schedule.name, schedule.cron, schedule.preset or "<default>")
    result = run_once(cfg)
    logging.info("[scheduler] '%s' finished with status=%s files=%d",
                 schedule.name, result.status, result.files_downloaded)


def serve(schedules: Optional[List[Schedule]] = None,
          base_cfg: Optional[Config] = None,
          *, tick_seconds: int = 30) -> None:
    """Run the scheduler loop until interrupted."""
    base_cfg = base_cfg or from_env()
    schedules = schedules if schedules is not None else load_schedules()
    if not schedules:
        raise SystemExit("No schedules configured. Set PDF_SCRAPER_SCHEDULES or presets/schedules.yaml")
    if croniter is None:
        raise SystemExit("croniter is required for the multi-schedule scheduler")

    next_runs: dict = {}
    logging.info("[scheduler] starting with %d schedule(s)", len(schedules))
    stop_event = threading.Event()
    try:
        while not stop_event.is_set():
            now = time.time()
            for sched in schedules:
                if not sched.enabled:
                    continue
                key = sched.name
                if key not in next_runs:
                    next_runs[key] = _next_run(sched.cron, now)
                if now >= next_runs[key]:
                    try:
                        run_schedule(sched, base_cfg)
                    except Exception as exc:
                        logging.exception("Schedule '%s' crashed: %s", sched.name, exc)
                    next_runs[key] = _next_run(sched.cron, time.time())
            time.sleep(tick_seconds)
    except KeyboardInterrupt:
        logging.info("[scheduler] interrupted, shutting down")
