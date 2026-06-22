"""Top-level orchestration used by CLI, scheduler, and web UI."""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

from . import cloud as cloud_mod
from . import feed as feed_mod
from . import healthcheck as healthcheck_mod
from . import webhook as webhook_mod
from .config import Config
from .crawler import crawl_pages_for_pdfs
from .downloader import download_pdf, make_session
from .reports import generate_html_report, merge_records, save_json_index
from .state import StateManager


@dataclass
class RunResult:
    started_at: str
    finished_at: str
    duration_seconds: float
    pages_crawled: int
    pdfs_found: int
    files_downloaded: int
    new_files: List[str] = field(default_factory=list)
    records: List[dict] = field(default_factory=list)
    cloud_uploaded: List[str] = field(default_factory=list)
    webhook_results: dict = field(default_factory=dict)
    feed_path: str = ""
    error: str = ""

    @property
    def status(self) -> str:
        return "ok" if not self.error else "error"

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 3),
            "pages_crawled": self.pages_crawled,
            "pdfs_found": self.pdfs_found,
            "files_downloaded": self.files_downloaded,
            "new_files": self.new_files,
            "records": self.records,
            "cloud_uploaded": self.cloud_uploaded,
            "webhook_results": self.webhook_results,
            "feed_path": self.feed_path,
            "error": self.error,
            "status": self.status,
        }


def run_once(cfg: Config, *, log: bool = True,
             progress_cb: Optional[Callable[[str, dict], None]] = None) -> RunResult:
    """Execute one crawl+download pass. Returns a :class:`RunResult`."""
    started = time.time()
    started_at = datetime.utcnow().isoformat() + "Z"
    result = RunResult(started_at=started_at, finished_at="",
                       duration_seconds=0.0, pages_crawled=0,
                       pdfs_found=0, files_downloaded=0)
    os.makedirs(cfg.output, exist_ok=True)

    log_path = cfg.log_file or os.path.join(cfg.output, "scraper.log")
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        force=True,
    )
    logging.info("Starting PDF Hunter run")

    state_path = cfg.state_file or os.path.join(cfg.output, ".state.json")
    state = StateManager(state_path)

    session = make_session(cfg.retry_total, cfg.backoff_factor)

    def _on_progress(**kw):
        if progress_cb:
            progress_cb("page", kw)
        result.pages_crawled += 1  # type: ignore[attr-defined]

    try:
        pdf_urls = crawl_pages_for_pdfs(
            session,
            cfg.urls,
            recursive=cfg.recursive,
            max_depth=cfg.max_depth,
            max_pages=cfg.max_pages,
            request_delay=cfg.request_delay,
            progress_cb=_on_progress,
            state=state,
        )
    except Exception as exc:
        result.error = f"crawler failed: {exc}"
        logging.exception(result.error)
        _finalize(cfg, state, result, started)
        return result

    result.pdfs_found = len(pdf_urls)
    logging.info("Found %d PDF URL(s)", len(pdf_urls))

    if not pdf_urls:
        _finalize(cfg, state, result, started)
        return result

    records: List[dict] = []
    records_lock = threading.Lock()
    counter = [0]
    tasks = [(u, src) for u, src in pdf_urls.values()]

    if cfg.workers and cfg.workers > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.workers) as ex:
            futures = []
            for task in tasks:
                s = make_session(cfg.retry_total, cfg.backoff_factor)
                futures.append(ex.submit(
                    download_pdf,
                    s, task[0], cfg.output, task[1], records, records_lock,
                    counter=counter,
                    max_retries=cfg.retry_total,
                    backoff_factor=cfg.backoff_factor,
                    ocr_enabled=cfg.ocr,
                    ocr_pages=cfg.ocr_pages,
                    state=state,
                ))
            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception as exc:
                    logging.warning("worker failed: %s", exc)
    else:
        for url, src in tasks:
            download_pdf(
                session, url, cfg.output, src, records, records_lock,
                counter=counter,
                max_retries=cfg.retry_total,
                backoff_factor=cfg.backoff_factor,
                ocr_enabled=cfg.ocr,
                ocr_pages=cfg.ocr_pages,
                state=state,
            )

    result.records = records
    result.new_files = [r["filename"] for r in records]
    result.files_downloaded = len(records)

    # Reports ----------------------------------------------------------------
    if records:
        html_path = os.path.join(cfg.output, "pdf_download_report.html")
        generate_html_report(html_path, records)
        index_path = os.path.join(cfg.output, "pdf_index.json")
        merged = merge_records(index_path, records)
        save_json_index(index_path, merged)

    # Cloud upload -----------------------------------------------------------
    if cfg.cloud.enabled and records:
        try:
            local_paths = [r["filepath"] for r in records]
            upload_result = cloud_mod.upload(local_paths, cfg.cloud)
            result.cloud_uploaded = list(upload_result.get("uploaded") or [])
        except Exception as exc:
            logging.warning("Cloud upload failed: %s", exc)

    # Feed -------------------------------------------------------------------
    if cfg.feed.enabled:
        try:
            index_path = os.path.join(cfg.output, "pdf_index.json")
            if os.path.exists(index_path):
                with open(index_path, encoding="utf-8") as fh:
                    full_records = json.load(fh)
            else:
                full_records = records
            feed_path = os.path.join(cfg.output, "feed.atom.xml")
            feed_mod.write_feed(full_records, cfg.feed, feed_path)
            result.feed_path = feed_path
        except Exception as exc:
            logging.warning("Feed generation failed: %s", exc)

    _finalize(cfg, state, result, started)
    return result


def _finalize(cfg: Config, state: StateManager, result: RunResult, started: float) -> None:
    result.finished_at = datetime.utcnow().isoformat() + "Z"
    result.duration_seconds = time.time() - started

    state.record_run(
        status=result.status,
        pages_crawled=result.pages_crawled,
        files_downloaded=result.files_downloaded,
    )
    state.save()

    healthcheck_mod.write_last_run(
        cfg.output,
        status=result.status,
        pages=result.pages_crawled,
        files=result.files_downloaded,
        duration_seconds=result.duration_seconds,
        error=result.error,
    )

    if cfg.webhook.enabled:
        msg = webhook_mod.format_summary(
            status=result.status,
            pages=result.pages_crawled,
            files=result.files_downloaded,
            duration=result.duration_seconds,
            new_files=result.new_files,
        )
        result.webhook_results = webhook_mod.send(cfg.webhook, msg)
