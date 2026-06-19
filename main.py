# Author: Scott Grivner
# Website: linktr.ee/scottgriv
# Abstract: Scrape a web page for PDF files and download them all locally.

# Import Modules
import argparse
import os
import re
import sys
from collections import deque
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
import logging
import time
import hashlib
import json
import PyPDF2
import threading
import concurrent.futures
try:
    from pdf2image import convert_from_path
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

# Default configuration
DEFAULT_URL = "https://ppid.unp.ac.id/"
DEFAULT_DOWNLOAD_FOLDER = r'./Downloads'
DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_PAGES = 100
ENV_FILE = ".env"

# List to store downloaded PDF filenames
downloaded_pdfs = []
pdf_count = 1  # Counter for unnamed PDFs


def load_env_file(env_path=ENV_FILE):
    """Load environment variables from a .env file if it exists."""
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


def parse_int_env(name, default):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def parse_bool_env(name):
    value = os.getenv(name, "").strip().lower()
    return value in ("1", "true", "yes", "on")


def get_unique_filename(folder, filename):
    """Ensures filename is unique by appending a number if the file already exists."""
    base, ext = os.path.splitext(filename)
    counter = 2
    new_filename = filename

    while os.path.exists(os.path.join(folder, new_filename)):
        new_filename = f"{base} ({counter}){ext}"
        counter += 1

    return os.path.join(folder, new_filename)


def get_pdf_filename(pdf_url, folder):
    """Extracts filename from URL or generates a default name if missing."""
    global pdf_count
    parsed_url = urlparse(pdf_url)
    filename = os.path.basename(parsed_url.path)

    if not filename or "." not in filename:
        filename = f"Downloaded_PDF_{pdf_count}.pdf"
        pdf_count += 1

    return get_unique_filename(folder, filename)


def normalize_page_url(page_url):
    """Normalize a URL for consistent page deduplication."""
    parsed = urlparse(page_url)
    scheme = parsed.scheme or "http"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    normalized = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
    return normalized.rstrip("/") if normalized != "/" else normalized


def normalize_pdf_url(pdf_url):
    """Normalize a PDF URL to avoid duplicate downloads."""
    parsed = urlparse(pdf_url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    normalized = urlunparse((scheme, netloc, parsed.path, parsed.params, parsed.query, ""))
    return normalized


def extract_pdf_metadata_text(filepath, ocr_enabled=False, ocr_pages=3):
    """Extract basic metadata and text from a PDF using PyPDF2."""
    meta = {}
    text_snippet = ""
    try:
        with open(filepath, 'rb') as fh:
            reader = PyPDF2.PdfReader(fh)
            docinfo = reader.metadata
            if docinfo:
                # convert keys to simple names
                try:
                    meta = {k[1:]: v for k, v in docinfo.items()}
                except Exception:
                    meta = {}

            # extract text from first few pages (limit to speed)
            texts = []
            for i, page in enumerate(reader.pages):
                if i >= 3:
                    break
                try:
                    t = page.extract_text() or ""
                    texts.append(t)
                except Exception:
                    continue
            text_snippet = "\n".join(texts).strip()
            # If no usable text and OCR requested, try OCR fallback
            if (not text_snippet or len(text_snippet.strip()) < 50) and ocr_enabled and OCR_AVAILABLE:
                try:
                    ocr_text = ocr_pdf(filepath, max_pages=ocr_pages)
                    if ocr_text:
                        text_snippet = ocr_text
                        meta['ocr_used'] = True
                except Exception:
                    pass
    except Exception:
        pass

    return meta, text_snippet


def ocr_pdf(filepath, max_pages=3, dpi=200):
    """Render PDF pages to images and run Tesseract OCR. Requires poppler and tesseract installed."""
    if not OCR_AVAILABLE:
        raise RuntimeError("OCR dependencies not available (pytesseract/pdf2image).")

    texts = []
    try:
        images = convert_from_path(filepath, dpi=dpi, first_page=1, last_page=max_pages)
        for img in images:
            try:
                txt = pytesseract.image_to_string(img)
                texts.append(txt)
            except Exception:
                continue
    except Exception as e:
        logging.warning(f"OCR conversion failed for {filepath}: {e}")

    return "\n".join(texts).strip()


def make_session(retry_total=3, backoff_factor=1):
    """Create a configured requests.Session with retry strategy."""
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/115.0 Safari/537.36"
        }
    )
    status_forcelist = (429, 500, 502, 503, 504)
    retry_strategy = Retry(
        total=retry_total,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        backoff_factor=backoff_factor,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


# Lock to protect shared records across threads
records_lock = threading.Lock()


def extract_pdf_candidates(html, soup, base_url):
    """Extract PDF URL candidates from HTML attributes and raw text."""
    candidates = set()
    pdf_attr_names = [
        "href",
        "src",
        "data-pdf",
        "data-src",
        "data-url",
        "data-file",
        "value",
        "poster",
    ]

    for tag in soup.find_all(True):
        for attr_name in pdf_attr_names:
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

    pdf_urls = set()
    for candidate in candidates:
        try:
            full_url = urljoin(base_url, candidate)
            if full_url.lower().startswith(("http://", "https://")) and ".pdf" in urlparse(full_url).path.lower():
                pdf_urls.add(full_url)
        except Exception:
            continue

    return sorted(pdf_urls)


def extract_internal_links(soup, base_url, base_domain):
    """Extract internal page links from anchors on the same domain."""
    links = set()
    for a_tag in soup.select("a[href]"):
        href = a_tag.get("href").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue

        try:
            full_url = urljoin(base_url, href)
        except Exception:
            continue

        parsed = urlparse(full_url)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc.lower() != base_domain:
            continue
        if parsed.path.lower().endswith(".pdf"):
            continue

        links.add(normalize_page_url(full_url))

    return sorted(links)


def crawl_pages_for_pdfs(session, start_urls, recursive, max_depth, max_pages, request_delay=0.0):
    """Crawl pages and collect PDF URLs from the same site."""
    visited_pages = set()
    pdf_urls = {}
    queue = deque([(normalize_page_url(url), 0) for url in start_urls])

    while queue and len(visited_pages) < max_pages:
        page_url, depth = queue.popleft()
        if page_url in visited_pages:
            continue

        print(f"Scanning page {len(visited_pages) + 1}/{max_pages} (depth {depth}): {page_url}")
        visited_pages.add(page_url)

        try:
            response = session.get(page_url, timeout=20)
            response.raise_for_status()
        except Exception as error:
            logging.warning(f"Failed to fetch page {page_url}: {error}")
            print(f"Failed to fetch page {page_url}: {error}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        page_pdf_urls = extract_pdf_candidates(response.text, soup, page_url)
        if page_pdf_urls:
            print(f"  Found {len(page_pdf_urls)} PDF URL(s) on this page.")
        for pdf_url in page_pdf_urls:
            normalized_pdf_url = normalize_pdf_url(pdf_url)
            if normalized_pdf_url not in pdf_urls:
                pdf_urls[normalized_pdf_url] = (pdf_url, page_url)

        if recursive and depth < max_depth:
            base_domain = urlparse(page_url).netloc.lower()
            internal_pages = extract_internal_links(soup, page_url, base_domain)
            if internal_pages:
                print(f"  Found {len(internal_pages)} internal link(s) to queue.")
            for internal_page in internal_pages:
                if internal_page not in visited_pages:
                    queue.append((internal_page, depth + 1))

        # respect simple rate limiting between page requests
        if request_delay and request_delay > 0:
            time.sleep(request_delay)

    return pdf_urls


def generate_html_report(report_path, records):
    """Generate an HTML report with PDF download insights."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for item in records:
        rows.append(
            f"<tr>"
            f"<td>{item['filename']}</td>"
            f"<td>{item['downloaded_at']}</td>"
            f"<td><a href=\"{item['source_page']}\" target=\"_blank\">Source</a></td>"
            f"<td><a href=\"{item['pdf_url']}\" target=\"_blank\">PDF Link</a></td>"
            f"<td>{item['filepath']}</td>"
            f"</tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>PDF Download Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f4f4f4; }}
        tr:nth-child(even) {{ background: #fafafa; }}
        a {{ color: #1a0dab; text-decoration: none; }}
    </style>
</head>
<body>
    <h1>PDF Download Report</h1>
    <p>Generated: {now}</p>
    <p>Total files downloaded: {len(records)}</p>
    <table>
        <thead>
            <tr>
                <th>Filename</th>
                <th>Downloaded At</th>
                <th>Source Page</th>
                <th>PDF Link</th>
                <th>Saved Path</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
</body>
</html>"""

    with open(report_path, 'w', encoding='utf-8') as report_file:
        report_file.write(html)


def download_pdf(session, pdf_url, folder, source_page, records, max_retries=3, backoff_factor=1.0, ocr_enabled=False, ocr_pages=3):
    """Download a single PDF file to the specified folder with resume and retries."""
    filename = get_pdf_filename(pdf_url, folder)
    temp_path = filename + ".part"

    # Determine existing size for resume
    existing_size = 0
    if os.path.exists(temp_path):
        existing_size = os.path.getsize(temp_path)

    # Try HEAD to get total size and content type
    total_size = None
    accept_ranges = False
    content_type = None
    ct = None
    try:
        head = session.head(pdf_url, timeout=15, allow_redirects=True)
        if head.status_code == 200:
            content_type = head.headers.get('Content-Type', '')
            cl = head.headers.get('Content-Length')
            if cl and cl.isdigit():
                total_size = int(cl)
            if head.headers.get('Accept-Ranges', '').lower() in ('bytes', 'yes'):
                accept_ranges = True
    except Exception:
        pass

    # If file already exists and size matches, skip
    if os.path.exists(filename):
        try:
            if total_size is None or os.path.getsize(filename) == total_size:
                logging.info(f"File exists and matches size, skipping: {filename}")
                print(f"Skipping (already downloaded): {filename}")
                return
        except Exception:
            pass

    attempt = 0
    while attempt <= max_retries:
        try:
            headers = {}
            mode = 'wb'
            if existing_size and accept_ranges:
                headers['Range'] = f'bytes={existing_size}-'
                mode = 'ab'

            with session.get(pdf_url, headers=headers, timeout=30, stream=True) as resp:
                resp.raise_for_status()
                # validate content-type early
                ct = resp.headers.get('Content-Type', '')
                if ct and 'pdf' not in ct.lower():
                    logging.warning(f"Content-Type for {pdf_url} is {ct}")

                # write to temp file (append if resuming)
                with open(temp_path, mode) as out_f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            out_f.write(chunk)

            # After download, move temp to final
            # Validate magic bytes
            valid = False
            try:
                with open(temp_path, 'rb') as chk:
                    start = chk.read(5)
                    if start.startswith(b'%PDF'):
                        valid = True
            except Exception:
                valid = False

            if not valid:
                logging.warning(f"Downloaded file failed PDF magic check: {pdf_url}")
                # If invalid, remove temp and raise
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
                raise ValueError('Invalid PDF content')

            os.replace(temp_path, filename)

            # record metadata and text
            with records_lock:
                downloaded_pdfs.append(filename)
            downloaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            meta, text_snippet = extract_pdf_metadata_text(filename, ocr_enabled=ocr_enabled, ocr_pages=ocr_pages)
            with records_lock:
                records.append(
                    {
                        "filename": os.path.basename(filename),
                        "filepath": filename,
                        "pdf_url": pdf_url,
                        "source_page": source_page,
                        "downloaded_at": downloaded_at,
                        "content_type": content_type or ct,
                        "size": os.path.getsize(filename),
                        "metadata": meta,
                        "text_snippet": text_snippet[:200],
                    }
                )
            print(f"  Saved to: {filename}")
            logging.info(f"Downloaded: {pdf_url} -> {filename}")
            return
        except Exception as error:
            attempt += 1
            wait = backoff_factor * (2 ** (attempt - 1))
            logging.warning(f"Attempt {attempt} failed for {pdf_url}: {error}; retrying in {wait}s")
            if attempt > max_retries:
                logging.error(f"Exceeded retries for {pdf_url}")
                print(f"Failed to download after retries: {pdf_url}")
                return
            time.sleep(wait)


def main():
    load_env_file()

    parser = argparse.ArgumentParser(
        description="Scrape web pages for PDF files and download them locally."
    )
    parser.add_argument(
        "--url",
        nargs="+",
        default=None,
        help="One or more website URLs to scan for PDF files.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Local folder where PDF files will be saved.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Scan internal links recursively on the same site.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum recursion depth when scanning internal links.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of pages to crawl when recursive scanning.",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Enable OCR fallback for scanned PDFs (requires Tesseract & poppler).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel download workers (default: 1 or env PDF_SCRAPER_WORKERS).",
    )
    args = parser.parse_args()

    env_urls = os.getenv("PDF_SCRAPER_URLS")
    if args.url:
        urls = args.url
    elif env_urls:
        urls = [url.strip() for url in env_urls.split(",") if url.strip()]
    else:
        urls = [DEFAULT_URL]

    folder_location = args.output or os.getenv("PDF_SCRAPER_OUTPUT") or DEFAULT_DOWNLOAD_FOLDER
    recursive = args.recursive or parse_bool_env("PDF_SCRAPER_RECURSIVE")
    max_depth = args.max_depth if args.max_depth is not None else parse_int_env("PDF_SCRAPER_MAX_DEPTH", DEFAULT_MAX_DEPTH)
    max_pages = args.max_pages if args.max_pages is not None else parse_int_env("PDF_SCRAPER_MAX_PAGES", DEFAULT_MAX_PAGES)
    ocr_enabled = args.ocr or parse_bool_env("PDF_SCRAPER_OCR")
    ocr_pages = parse_int_env("PDF_SCRAPER_OCR_PAGES", 3)
    workers = args.workers if args.workers is not None else parse_int_env("PDF_SCRAPER_WORKERS", 1)

    if not os.path.exists(folder_location):
        os.makedirs(folder_location, exist_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/115.0 Safari/537.36"
        }
    )

    # Configure retries and backoff for the session
    retry_total = parse_int_env("PDF_SCRAPER_RETRY_TOTAL", 3)
    backoff_factor = parse_int_env("PDF_SCRAPER_BACKOFF_FACTOR", 1)
    status_forcelist = (429, 500, 502, 503, 504)
    retry_strategy = Retry(
        total=retry_total,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        backoff_factor=backoff_factor,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Rate limiting between requests (seconds)
    request_delay = float(os.getenv("PDF_SCRAPER_REQUEST_DELAY", "0.5"))

    # Setup basic logging to file inside output folder
    log_path = os.path.join(folder_location, "scraper.log")
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logging.info("Starting PDF Hunter run")

    pdf_urls = crawl_pages_for_pdfs(
        session,
        urls,
        recursive=recursive,
        max_depth=max_depth,
        max_pages=max_pages,
        request_delay=request_delay,
    )

    if not pdf_urls:
        print("No PDF URLs found on the provided page(s).")
        sys.exit(0)

    print(f"Found {len(pdf_urls)} PDF URL(s). Starting download...")
    downloaded_records = []

    # Parallel download worker function
    def _download_task(task):
        pdf_url, source_page = task
        s = make_session(retry_total=retry_total, backoff_factor=backoff_factor)
        try:
            download_pdf(
                s,
                pdf_url,
                folder_location,
                source_page,
                downloaded_records,
                max_retries=retry_total,
                backoff_factor=backoff_factor,
                ocr_enabled=ocr_enabled,
                ocr_pages=ocr_pages,
            )
        except Exception as e:
            logging.exception(f"Worker failed for {pdf_url}: {e}")

    tasks = [(v[0], v[1]) for v in pdf_urls.values()]
    if workers and workers > 1:
        print(f"Downloading with {workers} workers...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for index, task in enumerate(tasks, start=1):
                pdf_url, _ = task
                print(f"Queueing ({index}/{len(tasks)}): {pdf_url}")
                futures.append(executor.submit(_download_task, task))

            # wait for completion and raise if any exceptions
            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass
    else:
        for index, task in enumerate(tasks, start=1):
            pdf_url, source_page = task
            print(f"Downloading ({index}/{len(tasks)}): {pdf_url}")
            _download_task(task)

    if downloaded_pdfs:
        print(f"\n{len(downloaded_pdfs)} PDF file(s) downloaded.")
        report_path = os.path.join(folder_location, "pdf_download_report.html")
        generate_html_report(report_path, downloaded_records)
        # save index JSON
        index_path = os.path.join(folder_location, "pdf_index.json")
        try:
            with open(index_path, 'w', encoding='utf-8') as jf:
                json.dump(downloaded_records, jf, ensure_ascii=False, indent=2)
            logging.info(f"Index saved: {index_path}")
        except Exception as e:
            logging.warning(f"Failed to save index: {e}")
        print(f"Report generated: {report_path}")
    else:
        print("\nNo PDF files downloaded.")


if __name__ == "__main__":
    main()
