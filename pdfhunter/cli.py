"""Command-line entry point for PDF Hunter.

Subcommands
-----------
``run``      crawl + download (default behaviour, preserves legacy CLI).
``serve``    start the FastAPI web UI + REST API.
``schedule`` run the multi-schedule scheduler.
``dry-run``  crawl only, do not download.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .config import from_env, load_preset, merge_cli
from .runner import run_once


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdfhunter",
        description="PDF Hunter: crawl the web for PDFs and download them.",
    )
    sub = parser.add_subparsers(dest="command")

    # run ------------------------------------------------------------------
    run = sub.add_parser("run", help="Run a crawl + download pass")
    run.add_argument("--url", nargs="+", default=None)
    run.add_argument("--output", default=None)
    run.add_argument("--recursive", action="store_true")
    run.add_argument("--max-depth", type=int, default=None)
    run.add_argument("--max-pages", type=int, default=None)
    run.add_argument("--ocr", action="store_true")
    run.add_argument("--workers", type=int, default=None)
    run.add_argument("--preset", default=None,
                     help="YAML preset to load before applying CLI overrides")
    run.add_argument("--json", action="store_true",
                     help="Print the RunResult as JSON to stdout")

    # dry-run --------------------------------------------------------------
    dry = sub.add_parser("dry-run", help="Crawl pages and print found PDFs")
    dry.add_argument("--url", nargs="+", default=None)
    dry.add_argument("--recursive", action="store_true")
    dry.add_argument("--max-depth", type=int, default=None)
    dry.add_argument("--max-pages", type=int, default=None)
    dry.add_argument("--preset", default=None)

    # serve ----------------------------------------------------------------
    serve = sub.add_parser("serve", help="Run the FastAPI web UI / API")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--preset", default=None)

    # schedule -------------------------------------------------------------
    sched = sub.add_parser("schedule", help="Run the multi-schedule scheduler")
    sched.add_argument("--preset", default=None)
    sched.add_argument("--tick", type=int, default=30)

    return parser


def _apply(args: argparse.Namespace) -> "Config":
    if getattr(args, "preset", None):
        cfg = load_preset(args.preset)
    else:
        cfg = from_env()
    overrides = {k: getattr(args, k, None) for k in (
        "url", "output", "recursive", "max_depth", "max_pages",
        "ocr", "workers",
    )}
    if "url" in overrides and overrides["url"]:
        cfg.urls = list(overrides.pop("url"))
    else:
        overrides.pop("url", None)
    return merge_cli(cfg, **overrides)


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command or "run"

    if command == "dry-run":
        from .crawler import crawl_pages_for_pdfs
        from .downloader import make_session
        cfg = _apply(args)
        session = make_session(cfg.retry_total, cfg.backoff_factor)
        pdfs = crawl_pages_for_pdfs(
            session, cfg.urls,
            recursive=cfg.recursive, max_depth=cfg.max_depth,
            max_pages=cfg.max_pages, request_delay=0.0,
        )
        print(json.dumps({
            "found": len(pdfs),
            "pdfs": [
                {"url": v[0], "source_page": v[1]} for v in pdfs.values()
            ],
        }, ensure_ascii=False, indent=2))
        return 0

    if command == "serve":
        from .webapp import main as serve_main
        cfg = _apply(args)
        if args.host:
            cfg.web_host = args.host
        if args.port:
            cfg.web_port = args.port
        serve_main()
        return 0

    if command == "schedule":
        from .scheduler import load_schedules, serve
        cfg = _apply(args)
        schedules = load_schedules()
        serve(schedules, cfg, tick_seconds=args.tick)
        return 0

    # run ------------------------------------------------------------------
    cfg = _apply(args)
    result = run_once(cfg)
    if getattr(args, "json", False):
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
