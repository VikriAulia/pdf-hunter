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
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse

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


def crawl_pages_for_pdfs(session, start_urls, recursive, max_depth, max_pages):
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


def download_pdf(session, pdf_url, folder, source_page, records):
    """Download a single PDF file to the specified folder."""
    filename = get_pdf_filename(pdf_url, folder)

    try:
        with session.get(pdf_url, timeout=20, stream=True) as pdf_response:
            pdf_response.raise_for_status()
            with open(filename, 'wb') as output_file:
                for chunk in pdf_response.iter_content(chunk_size=8192):
                    if chunk:
                        output_file.write(chunk)
        downloaded_pdfs.append(filename)
        downloaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        records.append(
            {
                "filename": os.path.basename(filename),
                "filepath": filename,
                "pdf_url": pdf_url,
                "source_page": source_page,
                "downloaded_at": downloaded_at,
            }
        )
        print(f"  Saved to: {filename}")
    except Exception as error:
        print(f"Failed to download {pdf_url}: {error}")


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

    if not os.path.exists(folder_location):
        os.makedirs(folder_location, exist_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/115.0 Safari/537.36"
        }
    )

    pdf_urls = crawl_pages_for_pdfs(
        session,
        urls,
        recursive=recursive,
        max_depth=max_depth,
        max_pages=max_pages,
    )

    if not pdf_urls:
        print("No PDF URLs found on the provided page(s).")
        sys.exit(0)

    print(f"Found {len(pdf_urls)} PDF URL(s). Starting download...")
    downloaded_records = []
    for index, (normalized_url, (pdf_url, source_page)) in enumerate(pdf_urls.items(), start=1):
        print(f"Downloading ({index}/{len(pdf_urls)}): {pdf_url}")
        download_pdf(session, pdf_url, folder_location, source_page, downloaded_records)

    if downloaded_pdfs:
        print(f"\n{len(downloaded_pdfs)} PDF file(s) downloaded.")
        report_path = os.path.join(folder_location, "pdf_download_report.html")
        generate_html_report(report_path, downloaded_records)
        print(f"Report generated: {report_path}")
    else:
        print("\nNo PDF files downloaded.")


if __name__ == "__main__":
    main()
