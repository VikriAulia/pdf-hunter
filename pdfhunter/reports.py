"""HTML and JSON report generators."""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Iterable, List


def generate_html_report(report_path: str, records: List[dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for item in records:
        rows.append(
            "<tr>"
            f"<td>{item['filename']}</td>"
            f"<td>{item['downloaded_at']}</td>"
            f"<td><a href=\"{item['source_page']}\" target=\"_blank\">Source</a></td>"
            f"<td><a href=\"{item['pdf_url']}\" target=\"_blank\">PDF Link</a></td>"
            f"<td>{item['filepath']}</td>"
            f"<td>{item.get('size', '')}</td>"
            "</tr>"
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
                <th>Size</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
</body>
</html>"""

    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return report_path


def save_json_index(path: str, records: List[dict]) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)
    return path


def merge_records(existing_path: str, new_records: Iterable[dict]) -> List[dict]:
    """Merge new records with an existing JSON index, deduplicating by sha256."""
    if not os.path.exists(existing_path):
        return list(new_records)
    try:
        with open(existing_path, encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, json.JSONDecodeError):
        old = []
    by_hash = {r.get("sha256"): r for r in old if r.get("sha256")}
    for rec in new_records:
        sha = rec.get("sha256")
        if sha:
            by_hash[sha] = rec
    return list(by_hash.values())
