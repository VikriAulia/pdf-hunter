"""Legacy entry point.

The implementation now lives in the ``pdfhunter`` package. This module
remains so existing cron jobs / Docker images keep working without any
change beyond a `pip install -r requirements.txt`.
"""
from __future__ import annotations

import sys

from pdfhunter.cli import main


if __name__ == "__main__":
    sys.exit(main())
