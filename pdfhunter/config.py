"""Centralised configuration loader for the PDF Hunter package.

Reads `.env` (if present) and exposes a single :func:`load_config` entry
point used by the CLI, scheduler, web UI, and tests.

Environment variables follow the legacy ``PDF_SCRAPER_*`` scheme so existing
deployments keep working without changes.
"""
from __future__ import annotations

import os
import yaml
from dataclasses import dataclass, field, asdict
from typing import List, Optional


DEFAULT_URL = "https://ppid.unp.ac.id/"
DEFAULT_DOWNLOAD_FOLDER = "./Downloads"
DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_PAGES = 100
DEFAULT_OCR_PAGES = 3
DEFAULT_RETRY_TOTAL = 3
DEFAULT_BACKOFF_FACTOR = 1
DEFAULT_REQUEST_DELAY = 0.5
DEFAULT_WORKERS = 1
DEFAULT_WEB_HOST = "0.0.0.0"
DEFAULT_WEB_PORT = 8080
DEFAULT_CRON_SCHEDULE = "0 2 * * *"

ENV_FILE = ".env"


def _parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_int(value, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_float(value, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_env_file(env_path: str = ENV_FILE) -> None:
    """Populate ``os.environ`` from a dotenv file (no override)."""
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


@dataclass
class WebhookConfig:
    enabled: bool = False
    discord_url: str = ""
    slack_url: str = ""
    telegram_token: str = ""
    telegram_chat_id: str = ""


@dataclass
class CloudConfig:
    enabled: bool = False
    backend: str = "s3"  # s3 | gdrive | none
    endpoint_url: str = ""
    region: str = ""
    access_key: str = ""
    secret_key: str = ""
    bucket: str = ""
    prefix: str = "pdfhunter"
    public_base_url: str = ""
    gdrive_folder_id: str = ""
    gdrive_credentials_file: str = ""


@dataclass
class FeedConfig:
    enabled: bool = False
    title: str = "PDF Hunter Feed"
    description: str = "Latest PDF documents harvested by PDF Hunter"
    link: str = "https://example.com/"
    author: str = "PDF Hunter"
    max_items: int = 100


@dataclass
class Config:
    urls: List[str] = field(default_factory=lambda: [DEFAULT_URL])
    output: str = DEFAULT_DOWNLOAD_FOLDER
    recursive: bool = False
    max_depth: int = DEFAULT_MAX_DEPTH
    max_pages: int = DEFAULT_MAX_PAGES
    ocr: bool = False
    ocr_pages: int = DEFAULT_OCR_PAGES
    workers: int = DEFAULT_WORKERS
    retry_total: int = DEFAULT_RETRY_TOTAL
    backoff_factor: int = DEFAULT_BACKOFF_FACTOR
    request_delay: float = DEFAULT_REQUEST_DELAY
    cron_schedule: str = DEFAULT_CRON_SCHEDULE

    incremental: bool = True
    state_file: str = "./Downloads/.state.json"

    web_host: str = DEFAULT_WEB_HOST
    web_port: int = DEFAULT_WEB_PORT

    log_file: str = ""

    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    cloud: CloudConfig = field(default_factory=CloudConfig)
    feed: FeedConfig = field(default_factory=FeedConfig)

    def as_dict(self) -> dict:
        data = asdict(self)
        return data


def from_env(env_path: Optional[str] = None) -> Config:
    """Build a :class:`Config` from environment variables."""
    if env_path:
        load_env_file(env_path)
    else:
        load_env_file()

    urls_env = os.getenv("PDF_SCRAPER_URLS", "")
    urls = [u.strip() for u in urls_env.split(",") if u.strip()] if urls_env else [DEFAULT_URL]

    cfg = Config(
        urls=urls,
        output=os.getenv("PDF_SCRAPER_OUTPUT", DEFAULT_DOWNLOAD_FOLDER),
        recursive=_parse_bool(os.getenv("PDF_SCRAPER_RECURSIVE"), False),
        max_depth=_parse_int(os.getenv("PDF_SCRAPER_MAX_DEPTH"), DEFAULT_MAX_DEPTH),
        max_pages=_parse_int(os.getenv("PDF_SCRAPER_MAX_PAGES"), DEFAULT_MAX_PAGES),
        ocr=_parse_bool(os.getenv("PDF_SCRAPER_OCR"), False),
        ocr_pages=_parse_int(os.getenv("PDF_SCRAPER_OCR_PAGES"), DEFAULT_OCR_PAGES),
        workers=_parse_int(os.getenv("PDF_SCRAPER_WORKERS"), DEFAULT_WORKERS),
        retry_total=_parse_int(os.getenv("PDF_SCRAPER_RETRY_TOTAL"), DEFAULT_RETRY_TOTAL),
        backoff_factor=_parse_int(os.getenv("PDF_SCRAPER_BACKOFF_FACTOR"), DEFAULT_BACKOFF_FACTOR),
        request_delay=_parse_float(os.getenv("PDF_SCRAPER_REQUEST_DELAY"), DEFAULT_REQUEST_DELAY),
        cron_schedule=os.getenv("CRON_SCHEDULE", DEFAULT_CRON_SCHEDULE),
        incremental=_parse_bool(os.getenv("PDF_SCRAPER_INCREMENTAL"), True),
        state_file=os.getenv("PDF_SCRAPER_STATE", "./Downloads/.state.json"),
        web_host=os.getenv("PDF_SCRAPER_WEB_HOST", DEFAULT_WEB_HOST),
        web_port=_parse_int(os.getenv("PDF_SCRAPER_WEB_PORT"), DEFAULT_WEB_PORT),
        log_file=os.getenv("PDF_SCRAPER_LOG", ""),
        webhook=WebhookConfig(
            enabled=_parse_bool(os.getenv("WEBHOOK_ENABLED"), False),
            discord_url=os.getenv("WEBHOOK_DISCORD_URL", ""),
            slack_url=os.getenv("WEBHOOK_SLACK_URL", ""),
            telegram_token=os.getenv("WEBHOOK_TELEGRAM_TOKEN", ""),
            telegram_chat_id=os.getenv("WEBHOOK_TELEGRAM_CHAT_ID", ""),
        ),
        cloud=CloudConfig(
            enabled=_parse_bool(os.getenv("CLOUD_ENABLED"), False),
            backend=os.getenv("CLOUD_BACKEND", "s3"),
            endpoint_url=os.getenv("CLOUD_ENDPOINT_URL", ""),
            region=os.getenv("CLOUD_REGION", ""),
            access_key=os.getenv("CLOUD_ACCESS_KEY", ""),
            secret_key=os.getenv("CLOUD_SECRET_KEY", ""),
            bucket=os.getenv("CLOUD_BUCKET", ""),
            prefix=os.getenv("CLOUD_PREFIX", "pdfhunter"),
            public_base_url=os.getenv("CLOUD_PUBLIC_BASE_URL", ""),
            gdrive_folder_id=os.getenv("CLOUD_GDRIVE_FOLDER_ID", ""),
            gdrive_credentials_file=os.getenv("CLOUD_GDRIVE_CREDENTIALS_FILE", ""),
        ),
        feed=FeedConfig(
            enabled=_parse_bool(os.getenv("FEED_ENABLED"), False),
            title=os.getenv("FEED_TITLE", "PDF Hunter Feed"),
            description=os.getenv("FEED_DESCRIPTION", "Latest PDF documents harvested by PDF Hunter"),
            link=os.getenv("FEED_LINK", "https://example.com/"),
            author=os.getenv("FEED_AUTHOR", "PDF Hunter"),
            max_items=_parse_int(os.getenv("FEED_MAX_ITEMS"), 100),
        ),
    )
    return cfg


def load_preset(path: str) -> Config:
    """Load configuration from a YAML preset file. Environment still wins."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    cfg = from_env()
    # shallow merge
    for section in ("urls", "output", "recursive", "max_depth", "max_pages",
                    "ocr", "ocr_pages", "workers", "retry_total",
                    "backoff_factor", "request_delay", "cron_schedule",
                    "incremental", "state_file", "web_host", "web_port",
                    "log_file"):
        if section in data and data[section] is not None:
            setattr(cfg, section, data[section])
    for section in ("webhook", "cloud", "feed"):
        if section in data and isinstance(data[section], dict):
            target = getattr(cfg, section)
            for k, v in data[section].items():
                if hasattr(target, k):
                    setattr(target, k, v)
    return cfg


def merge_cli(cfg: Config, **overrides) -> Config:
    """Apply CLI overrides on top of an existing :class:`Config`."""
    for key, value in overrides.items():
        if value is None:
            continue
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    return cfg
