"""Incremental state manager.

Persists the set of visited pages and downloaded PDF hashes so subsequent
runs only fetch what is new or changed. State lives in a JSON file next to
the downloads and is updated atomically.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Dict, Iterable, Set


class StateManager:
    """Thread-safe incremental state container."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._data: Dict[str, object] = {
            "version": 1,
            "visited_pages": [],          # type: ignore[assignment]
            "downloaded": {},             # url -> {filename, sha256, size, mtime}
            "last_run": None,             # ISO8601 string
            "last_status": "never",
            "pages_crawled": 0,
            "files_downloaded": 0,
        }
        self._load()

    # ------------------------------------------------------------------ I/O
    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._data.update({k: v for k, v in data.items() if k in self._data})
        except (OSError, json.JSONDecodeError):
            # corrupt state -> start fresh but back the file up
            try:
                os.replace(self.path, self.path + ".corrupt")
            except OSError:
                pass

    def save(self) -> None:
        with self._lock:
            tmp = self.path + ".tmp"
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    # ------------------------------------------------------------- accessors
    @property
    def visited_pages(self) -> Set[str]:
        return set(self._data.get("visited_pages") or [])  # type: ignore[arg-type]

    def mark_page_visited(self, url: str) -> None:
        with self._lock:
            pages = list(self._data.get("visited_pages") or [])
            if url not in pages:
                pages.append(url)
                self._data["visited_pages"] = pages

    def is_pdf_known(self, url: str) -> bool:
        return url in (self._data.get("downloaded") or {})

    def pdf_record(self, url: str) -> Dict[str, object]:
        return (self._data.get("downloaded") or {}).get(url, {})  # type: ignore[return-value]

    def pdf_hash_matches(self, url: str, sha256: str) -> bool:
        rec = self.pdf_record(url)
        return bool(rec) and rec.get("sha256") == sha256

    def register_pdf(self, url: str, *, filename: str, sha256: str, size: int) -> None:
        with self._lock:
            downloaded = dict(self._data.get("downloaded") or {})
            downloaded[url] = {
                "filename": filename,
                "sha256": sha256,
                "size": size,
                "mtime": int(time.time()),
            }
            self._data["downloaded"] = downloaded

    # ----------------------------------------------------------------- stats
    def record_run(self, *, status: str, pages_crawled: int, files_downloaded: int) -> None:
        from datetime import datetime, timezone
        with self._lock:
            self._data["last_run"] = datetime.now(timezone.utc).isoformat()
            self._data["last_status"] = status
            self._data["pages_crawled"] = pages_crawled
            self._data["files_downloaded"] = files_downloaded

    @property
    def last_run(self) -> str:
        return self._data.get("last_run") or ""  # type: ignore[return-value]

    @property
    def last_status(self) -> str:
        return self._data.get("last_status") or "never"  # type: ignore[return-value]

    def as_dict(self) -> dict:
        return dict(self._data)

    def known_urls(self) -> Iterable[str]:
        return (self._data.get("downloaded") or {}).keys()  # type: ignore[union-attr]
