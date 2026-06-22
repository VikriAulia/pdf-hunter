"""FastAPI web UI + REST API for PDF Hunter."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict
from typing import Dict, List, Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import healthcheck as healthcheck_mod
from .config import Config, from_env, merge_cli
from .runner import run_once
from .state import StateManager


HERE = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(HERE, "templates")
STATIC_DIR = os.path.join(HERE, "static")


def create_app(initial_config: Optional[Config] = None) -> FastAPI:
    cfg = initial_config or from_env()
    cfg_lock = threading.Lock()

    app = FastAPI(title="PDF Hunter", version="1.0")
    app.state.config = cfg
    app.state.jobs: Dict[str, dict] = {}

    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # --------------------------------------------------------------------- UI
    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        with cfg_lock:
            current = asdict(app.state.config)
        state_path = app.state.config.state_file
        state = StateManager(state_path) if state_path else StateManager(
            os.path.join(app.state.config.output, ".state.json"),
        )
        info = healthcheck_mod.read_last_run(app.state.config.output)
        jobs = list(app.state.jobs.values())[::-1]
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "config": current,
                "last_run": info,
                "state": state.as_dict(),
                "jobs": jobs,
            },
        )

    @app.get("/report", response_class=HTMLResponse)
    def report_page():
        path = os.path.join(app.state.config.output, "pdf_download_report.html")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Report not generated yet")
        with open(path, encoding="utf-8") as fh:
            return HTMLResponse(fh.read())

    @app.get("/index.json")
    def index_json():
        path = os.path.join(app.state.config.output, "pdf_index.json")
        if not os.path.exists(path):
            return JSONResponse({"records": []})
        with open(path, encoding="utf-8") as fh:
            return JSONResponse(json.load(fh))

    @app.get("/api/state")
    def api_state():
        state_path = app.state.config.state_file or os.path.join(app.state.config.output, ".state.json")
        state = StateManager(state_path)
        return JSONResponse(state.as_dict())

    @app.get("/api/search")
    def api_search(q: Optional[str] = None, limit: int = 100):
        path = os.path.join(app.state.config.output, "pdf_index.json")
        if not os.path.exists(path):
            return JSONResponse({"total": 0, "results": []})
        with open(path, encoding="utf-8") as fh:
            records = json.load(fh)
        if q:
            query = q.strip().lower()
            records = [
                rec for rec in records
                if query in str(rec.get("filename", "")).lower()
                or query in str(rec.get("pdf_url", "")).lower()
                or query in str(rec.get("source_page", "")).lower()
                or query in str(rec.get("filepath", "")).lower()
            ]
        return JSONResponse({"total": len(records), "results": records[:limit]})

    @app.get("/log")
    def log_tail():
        path = os.path.join(app.state.config.output, "scraper.log")
        if not os.path.exists(path):
            return JSONResponse({"log": ""})
        with open(path, encoding="utf-8", errors="replace") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(size - 16_384, 0))
            return JSONResponse({"log": fh.read()})

    @app.get("/feed.atom.xml")
    def feed():
        path = os.path.join(app.state.config.output, "feed.atom.xml")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Feed not generated yet")
        return FileResponse(path, media_type="application/atom+xml")

    # ------------------------------------------------------------------- API
    @app.get("/api/config")
    def api_config():
        return JSONResponse(asdict(app.state.config))

    @app.post("/api/config")
    async def api_config_update(payload: dict):
        with cfg_lock:
            for key, value in payload.items():
                if hasattr(app.state.config, key):
                    setattr(app.state.config, key, value)
        return JSONResponse({"ok": True, "config": asdict(app.state.config)})

    @app.get("/api/health")
    def api_health():
        info = healthcheck_mod.read_last_run(app.state.config.output)
        return JSONResponse({
            "healthy": healthcheck_mod.is_healthy(app.state.config.output),
            "info": info,
        })

    def _run_job(job_id: str, cfg: Config) -> None:
        def emit(event: str, data: dict):
            app.state.jobs[job_id].setdefault("events", []).append(
                {"ts": time.time(), "event": event, "data": data},
            )
        result = run_once(cfg, progress_cb=lambda e, d: emit(e, d))
        app.state.jobs[job_id]["status"] = result.status
        app.state.jobs[job_id]["finished_at"] = result.finished_at
        app.state.jobs[job_id]["duration_seconds"] = round(result.duration_seconds, 3)
        app.state.jobs[job_id]["files_downloaded"] = result.files_downloaded
        app.state.jobs[job_id]["result"] = result.to_dict()

    @app.post("/api/jobs")
    def api_jobs_start(payload: Optional[dict] = None, background_tasks: BackgroundTasks = None):
        overrides = payload or {}
        cfg = from_env()
        merge_cli(cfg, **{
            "urls": overrides.get("urls"),
            "output": overrides.get("output"),
            "recursive": overrides.get("recursive"),
            "max_depth": overrides.get("max_depth"),
            "max_pages": overrides.get("max_pages"),
            "ocr": overrides.get("ocr"),
            "workers": overrides.get("workers"),
            "incremental": overrides.get("incremental"),
        })
        cfg.output = overrides.get("output", cfg.output)
        cfg.webhook.enabled = False  # avoid duplicates when triggered manually
        job_id = uuid.uuid4().hex[:12]
        app.state.jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "started_at": time.time(),
            "events": [],
            "config": asdict(cfg),
        }
        thread = threading.Thread(
            target=_run_job, args=(job_id, cfg), daemon=True,
        )
        thread.start()
        return JSONResponse({"job_id": job_id})

    @app.get("/api/jobs")
    def api_jobs_list():
        return JSONResponse(list(app.state.jobs.values()))

    @app.get("/api/jobs/{job_id}")
    def api_jobs_get(job_id: str):
        job = app.state.jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="unknown job")
        return JSONResponse(job)

    @app.post("/api/dry-run")
    def api_dry_run(payload: Optional[dict] = None):
        from .crawler import crawl_pages_for_pdfs
        cfg = from_env()
        merge_cli(cfg, **{
            "urls": (payload or {}).get("urls"),
            "recursive": (payload or {}).get("recursive"),
            "max_depth": (payload or {}).get("max_depth"),
            "max_pages": (payload or {}).get("max_pages"),
        })
        from .downloader import make_session
        session = make_session(cfg.retry_total, cfg.backoff_factor)
        pdfs = crawl_pages_for_pdfs(
            session, cfg.urls,
            recursive=cfg.recursive, max_depth=cfg.max_depth,
            max_pages=cfg.max_pages, request_delay=0.0,
        )
        return JSONResponse({"found": len(pdfs), "pdfs": [
            {"url": v[0], "source_page": v[1]} for v in pdfs.values()
        ]})

    @app.post("/api/webhook/test")
    def api_webhook_test(payload: dict):
        from . import webhook as webhook_mod
        from .config import WebhookConfig
        wh = WebhookConfig(
            enabled=True,
            discord_url=payload.get("discord_url", ""),
            slack_url=payload.get("slack_url", ""),
            telegram_token=payload.get("telegram_token", ""),
            telegram_chat_id=payload.get("telegram_chat_id", ""),
        )
        msg = payload.get("message", "PDF Hunter webhook test ✅")
        return JSONResponse(webhook_mod.send(wh, msg))

    return app


def main() -> None:
    """Entry point used by ``python -m pdfhunter.webapp`` and the CLI."""
    import uvicorn  # type: ignore
    cfg = from_env()
    app = create_app(cfg)
    uvicorn.run(app, host=cfg.web_host, port=cfg.web_port, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    main()
