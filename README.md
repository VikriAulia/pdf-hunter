<!-- Begin README -->

<h1 align="center">Python PDF Web Scraper</h1>

A simple Python script that scrapes web pages for PDF files and downloads them to a local directory.

---------------

## Table of Contents

- [Getting Started](#getting-started)
- [Disclaimer](#disclaimer)
- [Resources](#resources)
- [License](#license)
- [Credits](#credits)

## Getting Started

1. Clone this repository.
2. Install [Python](https://www.python.org/downloads/).
3. Install [Pip](https://pip.pypa.io/en/stable/installing/).
4. Install the required packages using:
```bash
pip install -r requirements.txt
```
5. Create a `.env` file or copy `.env.example` and update the values.

Example `.env` values:
```env
PDF_SCRAPER_URLS=https://yourWebsiteURL,https://anotherSite.com
PDF_SCRAPER_OUTPUT=./Downloads
PDF_SCRAPER_RECURSIVE=true
PDF_SCRAPER_MAX_DEPTH=2
PDF_SCRAPER_MAX_PAGES=100
```

6. Run the script:
```bash
python main.py
```

7. Optional command-line overrides:
```bash
python main.py --url https://yourWebsiteURL https://anotherSite.com --output ./Downloads
```

8. To scan internal links recursively:
```bash
python main.py --url https://yourWebsiteURL --recursive --max-depth 2 --output ./Downloads
```

9. The program will show progress while scanning pages and downloading files.
10. After completion, it will generate a report at `./Downloads/pdf_download_report.html`.

## Cron / Scheduled Updates
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

## Disclaimer

> [!IMPORTANT]
> This tool is not intended to break copyright laws and is for personal use only. It merely automates the retrieval of publicly available data using standard web scraping techniques.
> The copyright of the data retrieved belongs to its respective owners, and I am not responsible for any illegal redistribution or misuse of data obtained using this tool.

> [!CAUTION]
> Use of this tool is at your own risk. By using this tool, you agree that you are solely responsible for any legal issues that may arise from your use of this tool.

## Resources

- [Python](https://www.python.org)
- [Pip](https://pip.pypa.io/en/stable/installing/)
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [Urllib3](https://urllib3.readthedocs.io/en/latest/)

## License

This project is released under the terms of **The Unlicense**, which allows you to use, modify, and distribute the code as you see fit. 
- [The Unlicense](https://choosealicense.com/licenses/unlicense/) removes traditional copyright restrictions, giving you the freedom to use the code in any way you choose.
- For more details, see the [LICENSE](LICENSE) file in this repository.

## Credits

**Author:** [Vikri Aulia](https://github.com/VikriAulia) <br>
**Email:** [vikriaulia@gmail.com](mailto:vikriaulia@gmail.com) <br>
**Website:** [linktr.ee/vikriaulia](https://www.linktr.ee/vikriaulia) <br>


---------------

<div align="center">
    <a href="https://linktr.ee/vikriaulia" target="_blank">
        <img src="https://ugc.production.linktr.ee/38807b3a-2daa-4378-8fc2-e6883a1729a0_1000240768.jpeg?io=true&size=avatar-v3_0" width="100" height="100"/>
    </a>
</div>

<!-- End README -->
