# Python PDF Web Scraper

A Python script that scrapes web pages for PDF files and downloads them to a local directory with support for recursive crawling, OCR fallback, parallel downloads, and report generation.

## Project Overview

This scraper crawls specified URLs, extracts PDF links, downloads the files, and generates reports. It supports:
- Recursive internal link crawling (same domain only)
- Parallel downloading with configurable worker count
- OCR fallback for scanned PDFs (requires Tesseract and Poppler)
- Retry mechanisms with exponential backoff
- Resume capability for interrupted downloads
- HTML report generation with download metadata
- JSON index file creation
- Environment variable configuration via `.env`

## Key Components

### main.py
The primary script containing all functionality:
- **Configuration Loading**: Loads settings from `.env` file and command-line arguments
- **URL Processing**: Handles single or multiple start URLs
- **Web Crawling**: Crawls pages to find PDF links using BeautifulSoup
- **PDF Extraction**: Finds PDF URLs from HTML attributes and raw text patterns
- **Download Management**: Handles PDF downloads with retry, resume, and validation
- **Metadata Extraction**: Extracts text and metadata from PDFs using PyPDF2 with OCR fallback
- **Report Generation**: Creates HTML reports and JSON indexes of downloaded files
- **Parallel Processing**: Uses ThreadPoolExecutor for concurrent downloads

### Core Functions
- `load_env_file()`: Loads environment variables from `.env`
- `crawl_pages_for_pdfs()`: Main crawling function that finds PDF URLs
- `extract_pdf_candidates()`: Extracts PDF links from HTML
- `extract_internal_links()`: Finds internal links for recursive crawling
- `download_pdf()`: Handles individual PDF downloads with retries
- `make_session()`: Creates configured requests session with retry strategy
- `generate_html_report()`: Creates HTML report of downloads
- `extract_pdf_metadata_text()`: Extracts text/metadata from PDFs
- `ocr_pdf()`: OCR fallback for scanned PDFs

## Installation & Usage

### Prerequisites
- Python 3.x
- Pip package manager
- For OCR functionality: Tesseract OCR and Poppler utilities

### Setup
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create `.env` file (copy from `.env.example`) or use command-line arguments
4. Run: `python main.py`

### Configuration Options
Set via environment variables (`.env`) or command-line arguments:

| Variable/Argument | Description | Default |
|-------------------|-------------|---------|
| `PDF_SCRAPER_URLS` / `--url` | Comma-separated list of URLs to scrape | `https://ppid.unp.ac.id/` |
| `PDF_SCRAPER_OUTPUT` / `--output` | Output directory for downloads | `./Downloads` |
| `PDF_SCRAPER_RECURSIVE` / `--recursive` | Enable recursive crawling | `false` |
| `PDF_SCRAPER_MAX_DEPTH` / `--max-depth` | Maximum recursion depth | `2` |
| `PDF_SCRAPER_MAX_PAGES` / `--max-pages` | Maximum pages to crawl | `100` |
| `PDF_SCRAPER_OCR` / `--ocr` | Enable OCR fallback | `false` |
| `PDF_SCRAPER_WORKERS` / `--workers` | Number of parallel download workers | `1` |
| `PDF_SCRAPER_RETRY_TOTAL` | Number of download retries | `3` |
| `PDF_SCRAPER_BACKOFF_FACTOR` | Backoff factor for retries | `1` |
| `PDF_SCRAPER_REQUEST_DELAY` | Delay between requests (seconds) | `0.5` |
| `PDF_SCRAPER_OCR_PAGES` | Max pages for OCR processing | `3` |

### Example `.env` File
```env
PDF_SCRAPER_URLS=https://example.com,https://anotherexample.com
PDF_SCRAPER_OUTPUT=./Downloads
PDF_SCRAPER_RECURSIVE=true
PDF_SCRAPER_MAX_DEPTH=2
PDF_SCRAPER_MAX_PAGES=100
PDF_SCRAPER_WORKERS=4
PDF_SCRAPER_OCR=true
PDF_SCRAPER_RETRY_TOTAL=3
PDF_SCRAPER_BACKOFF_FACTOR=1
PDF_SCRAPER_REQUEST_DELAY=0.5
PDF_SCRAPER_OCR_PAGES=3
```

### Example Command-Line Usage
```bash
# Basic usage with defaults
python main.py

# Custom URLs and output
python main.py --url https://example.com --output ./my_pdfs

# Recursive crawling with parallel downloads
python main.py --url https://example.com --recursive --max-depth 3 --workers 4

# With OCR fallback
python main.py --url https://example.com --ocr --workers 2
```

### Cron / Scheduled Updates
If you want the script to run periodically, add a cron job on Linux/macOS. Example runs every day at 02:00:
```cron
0 2 * * * cd /path/to/python-pdf_web_scraper && /usr/bin/python main.py >> /path/to/python-pdf_web_scraper/cron.log 2>&1
```

If you use a `.env` file, place it in the repository folder and the script will load it automatically when run from that directory.

If you want to pass arguments directly in cron instead of using `.env`:
```cron
0 2 * * * cd /path/to/python-pdf_web_scraper && /usr/bin/python main.py --url https://yourWebsiteURL --recursive --max-depth 2 --output ./Downloads >> /path/to/python-pdf_web_scraper/cron.log 2>&1
```

To edit cron jobs, run `crontab -e` and add the desired schedule line.

## Output Files

After running the scraper, the output directory will contain:
- Downloaded PDF files
- `pdf_download_report.html`: HTML report with download details
- `pdf_index.json`: JSON index of all downloaded PDFs with metadata
- `scraper.log`: Log file of the scraping session

## Dependencies

See `requirements.txt` for Python package dependencies:
- `beautifulsoup4`: HTML parsing
- `urllib3`: HTTP utilities
- `requests`: HTTP client
- `PyPDF2`: PDF text/metadata extraction
- `pytesseract`: OCR interface (requires Tesseract OCR installed)
- `pdf2image`: PDF to image conversion (requires Poppler installed)
- `Pillow`: Image processing for OCR

## How It Works

1. **Initialization**: Loads configuration from `.env` and command-line arguments
2. **Session Setup**: Creates HTTP session with retry strategy and headers
3. **Logging**: Sets up log file in output directory
4. **Crawling**: 
   - Starts with provided URLs
   - Extracts PDF links from each page
   - If recursive, finds internal links on same domain and continues crawling
   - Respects max depth and max pages limits
5. **Download Processing**:
   - Normalizes URLs to avoid duplicates
   - Downloads PDFs with retry and resume capability
   - Validates PDF magic bytes (%PDF)
   - Extracts metadata and text (with OCR fallback if enabled)
6. **Reporting**: Generates HTML report and JSON index of downloads
7. **Completion**: Prints summary and exits

## Error Handling & Resilience

- Network retries with exponential backoff
- Resume capability for interrupted downloads (partial files)
- PDF validation via magic bytes
- Graceful handling of missing OCR dependencies
- Detailed logging to file and console
- Thread-safe shared state using locks

## Environment Variables

All environment variables are loaded from `.env` file if present:
- `PDF_SCRAPER_URLS`: Comma-separated list of URLs to scrape
- `PDF_SCRAPER_OUTPUT`: Output directory path
- `PDF_SCRAPER_RECURSIVE`: "true"/"false" for recursive crawling
- `PDF_SCRAPER_MAX_DEPTH`: Integer for maximum recursion depth
- `PDF_SCRAPER_MAX_PAGES`: Integer for maximum pages to crawl
- `PDF_SCRAPER_WORKERS`: Integer for number of parallel workers
- `PDF_SCRAPER_RETRY_TOTAL`: Integer for download retry attempts
- `PDF_SCRAPER_BACKOFF_FACTOR`: Integer for backoff multiplier
- `PDF_SCRAPER_REQUEST_DELAY`: Float for delay between requests
- `PDF_SCRAPER_OCR`: "true"/"false" to enable OCR fallback
- `PDF_SCRAPER_OCR_PAGES`: Integer for max OCR pages per PDF

## Maintenance Notes

- The script uses global variables for tracking downloaded files (`downloaded_pdfs`, `pdf_count`)
- Thread safety is maintained with `records_lock` for shared records
- OCR functionality requires external dependencies (Tesseract OCR, Poppler)
- For large-scale scraping, adjust workers, delays, and limits appropriately
- The scraper respects same-domain only for recursive crawling to avoid unintended external links
- PDF validation prevents saving corrupted or non-PDF files

## License

This project is released under The Unlicense - see [LICENSE](LICENSE) file for details.