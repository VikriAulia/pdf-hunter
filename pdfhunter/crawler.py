"""Crawler that discovers PDF URLs on a set of pages.

Adapted from the original ``main.py`` crawler but factored out for reuse
from both the CLI and the web UI. All public helpers are stateless and
take a ``requests.Session`` so they can be shared or replaced in tests.
"""
from __future__ import annotations

import logging
import re
import time
from collections import deque
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .utils import normalize_page_url, normalize_pdf_url


PDF_ATTRS = (
    "href", "src", "data-pdf", "data-src", "data-url",
    "data-file", "value", "poster", "action",
)


def extract_pdf_candidates(html: str, soup: BeautifulSoup, base_url: str) -> List[str]:
    """Collect PDF URLs from HTML attributes and raw text patterns."""
    candidates: Set[str] = set()
    for tag in soup.find_all(True):
        for attr_name in PDF_ATTRS:
            attr_value = tag.get(attr_name)
            if isinstance(attr_value, str) and ".pdf" in attr_value.lower():
                candidates.add(attr_value.strip())
            elif isinstance(attr_value, list):
                for item in attr_value:
                    if isinstance(item, str) and ".pdf" in item.lower():
                        candidates.add(item.strip())
        for attr_value in tag.attrs.values():
            if isinstance(attr_value, str) and ".pdf" in attr_value.lower():
                candidates.add(attr_value.strip())
            elif isinstance(attr_value, list):
                for item in attr_value:
                    if isinstance(item, str) and ".pdf" in item.lower():
                        candidates.add(item.strip())

    candidates.update(re.findall(r'https?://[^"\'\s<>]+\.pdf(?:\?[^"\'\s<>]*)?', html, flags=re.I))
    candidates.update(re.findall(r'(?<=["\"]).*?\.pdf(?:\?[^"\'\s<>]*)?(?=["\"])', html, flags=re.I))

    pdf_urls: Set[str] = set()
    for cand in candidates:
        try:
            full = urljoin(base_url, cand)
            parsed = urlparse(full)
            if parsed.scheme in ("http", "https") and ".pdf" in parsed.path.lower():
                pdf_urls.add(full)
        except Exception:
            continue
    return sorted(pdf_urls)


def extract_internal_links(soup: BeautifulSoup, base_url: str, base_domain: str) -> List[str]:
    """Same-domain anchor links that are not PDFs themselves."""
    links: Set[str] = set()
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        try:
            full = urljoin(base_url, href)
        except Exception:
            continue
        parsed = urlparse(full)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc.lower() != base_domain.lower():
            continue
        if parsed.path.lower().endswith(".pdf"):
            continue
        links.add(normalize_page_url(full))
    return sorted(links)


def crawl_pages_for_pdfs(
    session: requests.Session,
    start_urls: List[str],
    *,
    recursive: bool = False,
    max_depth: int = 2,
    max_pages: int = 100,
    request_delay: float = 0.0,
    progress_cb=None,
    state=None,
) -> Dict[str, Tuple[str, str]]:
    """Crawl pages and collect PDF URLs.

    Returns a mapping ``normalized_pdf_url -> (original_url, source_page)``.
    """
    visited: Set[str] = set()
    pdf_urls: Dict[str, Tuple[str, str]] = {}
    queue: deque = deque()

    for u in start_urls:
        n = normalize_page_url(u)
        if n not in visited:
            queue.append((n, 0))

    while queue and len(visited) < max_pages:
        page_url, depth = queue.popleft()
        if page_url in visited:
            continue
        if state is not None:
            state.mark_page_visited(page_url)
        visited.add(page_url)

        if progress_cb:
            progress_cb(page=page_url, depth=depth, visited=len(visited), max_pages=max_pages)

        try:
            response = session.get(page_url, timeout=20)
            response.raise_for_status()
        except Exception as error:
            logging.warning("Failed to fetch %s: %s", page_url, error)
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        page_pdfs = extract_pdf_candidates(response.text, soup, page_url)
        for pdf_url in page_pdfs:
            norm = normalize_pdf_url(pdf_url)
            if norm not in pdf_urls:
                pdf_urls[norm] = (pdf_url, page_url)

        if recursive and depth < max_depth:
            base_domain = urlparse(page_url).netloc.lower()
            for link in extract_internal_links(soup, page_url, base_domain):
                if link not in visited:
                    queue.append((link, depth + 1))

        if request_delay and request_delay > 0:
            time.sleep(request_delay)

    return pdf_urls
