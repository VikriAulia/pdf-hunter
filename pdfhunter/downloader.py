"""Download PDFs with retry, resume, and hash verification."""
from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .extractor import extract_pdf_metadata_text
from .utils import normalize_pdf_url


def make_session(retry_total: int = 3, backoff_factor: float = 1.0,
                 user_agent: Optional[str] = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {"User-Agent": user_agent or
         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/115.0 Safari/537.36"}
    )
    retry = Retry(
        total=retry_total,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        backoff_factor=backoff_factor,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_unique_filename(folder: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    counter = 2
    candidate = filename
    while os.path.exists(os.path.join(folder, candidate)):
        candidate = f"{base} ({counter}){ext}"
        counter += 1
    return os.path.join(folder, candidate)


def get_pdf_filename(pdf_url: str, folder: str, counter: List[int]) -> str:
    from urllib.parse import urlparse
    name = os.path.basename(urlparse(pdf_url).path)
    if not name or "." not in name:
        counter[0] += 1
        name = f"Downloaded_PDF_{counter[0]}.pdf"
    return get_unique_filename(folder, name)


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_pdf(
    session: requests.Session,
    pdf_url: str,
    folder: str,
    source_page: str,
    records: List[dict],
    records_lock,
    *,
    counter: Optional[List[int]] = None,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    ocr_enabled: bool = False,
    ocr_pages: int = 3,
    state=None,
    on_success: Optional[Callable[[dict], None]] = None,
) -> Optional[dict]:
    """Download a single PDF with retries, resume, and magic-byte validation.

    Returns the downloaded record dict on success, ``None`` on failure or skip.
    """
    counter = counter if counter is not None else [0]
    filename = get_pdf_filename(pdf_url, folder, counter)
    temp_path = filename + ".part"

    existing_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0

    total_size: Optional[int] = None
    accept_ranges = False
    content_type: Optional[str] = None
    try:
        head = session.head(pdf_url, timeout=15, allow_redirects=True)
        if head.status_code == 200:
            content_type = head.headers.get("Content-Type", "")
            cl = head.headers.get("Content-Length")
            if cl and cl.isdigit():
                total_size = int(cl)
            if head.headers.get("Accept-Ranges", "").lower() in ("bytes", "yes"):
                accept_ranges = True
    except Exception:
        pass

    if os.path.exists(filename):
        try:
            if total_size is None or os.path.getsize(filename) == total_size:
                if state is not None:
                    state.register_pdf(
                        pdf_url,
                        filename=os.path.basename(filename),
                        sha256=_hash_file(filename) if os.path.getsize(filename) > 0 else "",
                        size=os.path.getsize(filename),
                    )
                logging.info("Skipping (already downloaded): %s", filename)
                return None
        except Exception:
            pass

    attempt = 0
    while attempt <= max_retries:
        attempt += 1
        try:
            headers = {}
            mode = "wb"
            if existing_size and accept_ranges:
                headers["Range"] = f"bytes={existing_size}-"
                mode = "ab"

            with session.get(pdf_url, headers=headers, timeout=30, stream=True) as resp:
                resp.raise_for_status()
                ct = resp.headers.get("Content-Type", "")
                with open(temp_path, mode) as out:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            out.write(chunk)

            valid = False
            try:
                with open(temp_path, "rb") as chk:
                    if chk.read(5).startswith(b"%PDF"):
                        valid = True
            except Exception:
                valid = False

            if not valid:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                raise ValueError("Invalid PDF content")

            os.replace(temp_path, filename)
            sha = _hash_file(filename)
            size = os.path.getsize(filename)

            meta, text_snippet = extract_pdf_metadata_text(
                filename, ocr_enabled=ocr_enabled, ocr_pages=ocr_pages,
            )

            downloaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            record = {
                "filename": os.path.basename(filename),
                "filepath": filename,
                "pdf_url": pdf_url,
                "source_page": source_page,
                "downloaded_at": downloaded_at,
                "content_type": content_type or ct,
                "size": size,
                "metadata": meta,
                "text_snippet": text_snippet[:200],
                "sha256": sha,
            }

            with records_lock:
                records.append(record)

            if state is not None:
                state.register_pdf(
                    pdf_url,
                    filename=record["filename"],
                    sha256=sha,
                    size=size,
                )

            if on_success:
                try:
                    on_success(record)
                except Exception:
                    logging.exception("on_success callback failed for %s", pdf_url)

            logging.info("Downloaded %s -> %s", pdf_url, filename)
            return record

        except Exception as exc:
            wait = backoff_factor * (2 ** (attempt - 1))
            logging.warning(
                "Attempt %s failed for %s: %s; retrying in %ss",
                attempt, pdf_url, exc, wait,
            )
            if attempt > max_retries:
                logging.error("Exceeded retries for %s", pdf_url)
                return None
            time.sleep(wait)

    return None
