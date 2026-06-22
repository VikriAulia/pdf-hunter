"""URL normalisation helpers shared by the crawler and state manager."""
from __future__ import annotations

from urllib.parse import urljoin, urlparse, urlunparse


def normalize_page_url(page_url: str) -> str:
    """Normalise a page URL so the same logical page collapses to one key."""
    parsed = urlparse(page_url)
    scheme = parsed.scheme or "http"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    normalized = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
    return normalized.rstrip("/") if normalized != "/" else normalized


def normalize_pdf_url(pdf_url: str) -> str:
    """Normalise a PDF URL (lower-cased scheme/host, no fragment)."""
    parsed = urlparse(pdf_url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    return urlunparse((scheme, netloc, parsed.path, parsed.params, parsed.query, ""))


def same_domain(url: str, base_domain: str) -> bool:
    return urlparse(url).netloc.lower() == base_domain.lower()


def safe_urljoin(base: str, href: str) -> str:
    return urljoin(base, href)
