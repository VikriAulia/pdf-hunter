"""RSS / Atom feed generator for newly harvested PDFs."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterable, List

try:
    from feedgen.feed import FeedGenerator  # type: ignore
except Exception:  # pragma: no cover
    FeedGenerator = None  # type: ignore

from .config import FeedConfig


def _to_iso(dt) -> str:
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=dt.tzinfo or timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def build_feed(records: Iterable[dict], cfg: FeedConfig) -> bytes:
    """Build an Atom feed from the given PDF records (newest first)."""
    records = sorted(records, key=lambda r: r.get("downloaded_at") or "", reverse=True)
    if cfg.max_items:
        records = records[: cfg.max_items]

    if FeedGenerator is None:
        # Tiny fallback Atom feed (no dependencies).
        items_xml = []
        for rec in records:
            items_xml.append(
                "<entry>"
                f"<title>{rec.get('filename', '')}</title>"
                f"<link href=\"{rec.get('pdf_url', '')}\"/>"
                f"<id>{rec.get('pdf_url', '')}</id>"
                f"<updated>{_to_iso(rec.get('downloaded_at'))}</updated>"
                f"<summary>{rec.get('source_page', '')}</summary>"
                "</entry>"
            )
        body = (
            "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<feed xmlns=\"http://www.w3.org/2005/Atom\">"
            f"<title>{cfg.title}</title>"
            f"<subtitle>{cfg.description}</subtitle>"
            f"<link href=\"{cfg.link}\"/>"
            f"<updated>{datetime.now(timezone.utc).isoformat()}</updated>"
            f"<author><name>{cfg.author}</name></author>"
            + "".join(items_xml) +
            "</feed>"
        )
        return body.encode("utf-8")

    fg = FeedGenerator()
    fg.id(cfg.link or "urn:pdfhunter")
    fg.title(cfg.title)
    fg.description(cfg.description)
    fg.link(href=cfg.link, rel="alternate")
    fg.language("en")
    fg.author({"name": cfg.author})
    fg.updated(datetime.now(timezone.utc))

    for rec in records:
        fe = fg.add_entry()
        fe.id(rec.get("pdf_url") or rec.get("filename", ""))
        fe.title(rec.get("filename", ""))
        fe.link(href=rec.get("pdf_url", ""))
        fe.summary(rec.get("source_page", ""))
        fe.updated(_to_iso(rec.get("downloaded_at")))
        fe.published(_to_iso(rec.get("downloaded_at")))
    return fg.atom_str(pretty=True).encode("utf-8") if hasattr(fg, "atom_str") else fg.atom_bytes()


def write_feed(records: Iterable[dict], cfg: FeedConfig, path: str) -> str:
    """Build a feed and write it to ``path``."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = build_feed(records, cfg)
    with open(path, "wb") as fh:
        fh.write(data)
    return path
