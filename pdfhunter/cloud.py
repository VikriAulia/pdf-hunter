"""Cloud uploaders: S3/MinIO (and Google Drive stubs)."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Iterable, List, Optional

from .config import CloudConfig


def _month_prefix(prefix: str) -> str:
    month = datetime.utcnow().strftime("%Y/%m")
    return f"{prefix.rstrip('/')}/{month}".strip("/")


def upload_s3(files: Iterable[str], cfg: CloudConfig) -> List[str]:
    """Upload files to an S3-compatible bucket. Returns uploaded keys."""
    if not cfg.bucket:
        raise ValueError("CLOUD_BUCKET is required for S3 uploads")
    try:
        import boto3  # type: ignore
    except Exception as exc:
        raise RuntimeError("boto3 is not installed") from exc

    session_kwargs = {}
    if cfg.region:
        session_kwargs["region_name"] = cfg.region
    if cfg.endpoint_url:
        session_kwargs["endpoint_url"] = cfg.endpoint_url
    if cfg.access_key and cfg.secret_key:
        session_kwargs["aws_access_key_id"] = cfg.access_key
        session_kwargs["aws_secret_access_key"] = cfg.secret_key

    s3 = boto3.client("s3", **session_kwargs)
    base = _month_prefix(cfg.prefix)
    uploaded: List[str] = []
    for local_path in files:
        if not os.path.exists(local_path):
            continue
        key = f"{base}/{os.path.basename(local_path)}"
        try:
            extra = {}
            if cfg.public_base_url:
                extra["ACL"] = "public-read"
            s3.upload_file(local_path, cfg.bucket, key, ExtraArgs=extra or None)
            uploaded.append(key)
        except Exception as exc:
            logging.warning("S3 upload failed for %s: %s", local_path, exc)
    return uploaded


def upload_gdrive(files: Iterable[str], cfg: CloudConfig) -> List[str]:
    """Upload files to Google Drive using a service-account credentials file.

    Requires ``google-api-python-client`` which is **optional**. Raises
    ``RuntimeError`` if it is missing so the caller can degrade gracefully.
    """
    if not cfg.gdrive_folder_id or not cfg.gdrive_credentials_file:
        raise ValueError("CLOUD_GDRIVE_FOLDER_ID and CLOUD_GDRIVE_CREDENTIALS_FILE are required")
    try:
        from googleapiclient.discovery import build  # type: ignore
        from googleapiclient.http import MediaFileUpload  # type: ignore
        from google.oauth2 import service_account  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Google API client libraries are not installed") from exc

    creds = service_account.Credentials.from_service_account_file(
        cfg.gdrive_credentials_file,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    uploaded: List[str] = []
    for local_path in files:
        if not os.path.exists(local_path):
            continue
        media = MediaFileUpload(local_path, resumable=False)
        file_meta = {"name": os.path.basename(local_path), "parents": [cfg.gdrive_folder_id]}
        try:
            service.files().create(body=file_meta, media_body=media, fields="id").execute()
            uploaded.append(os.path.basename(local_path))
        except Exception as exc:
            logging.warning("Drive upload failed for %s: %s", local_path, exc)
    return uploaded


def upload(files: Iterable[str], cfg: CloudConfig) -> dict:
    """Dispatch to the configured backend. Returns ``{"backend": [...keys]}``."""
    if not cfg.enabled:
        return {}
    backend = (cfg.backend or "s3").lower()
    files = list(files)
    if backend == "s3":
        return {"backend": "s3", "uploaded": upload_s3(files, cfg)}
    if backend == "gdrive":
        return {"backend": "gdrive", "uploaded": upload_gdrive(files, cfg)}
    raise ValueError(f"Unknown cloud backend: {cfg.backend}")


def public_links(keys: Iterable[str], cfg: CloudConfig) -> List[str]:
    keys = list(keys)
    if not keys:
        return []
    backend = (cfg.backend or "s3").lower()
    if backend == "s3" and cfg.public_base_url:
        base = cfg.public_base_url.rstrip("/")
        return [f"{base}/{k}" for k in keys]
    return [f"s3://{cfg.bucket}/{k}" for k in keys]
