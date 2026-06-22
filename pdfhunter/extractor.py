"""PDF metadata + text extraction with optional OCR fallback."""
from __future__ import annotations

import logging

try:
    import PyPDF2  # type: ignore
except Exception:  # pragma: no cover - PyPDF2 is mandatory in requirements
    PyPDF2 = None  # type: ignore

try:
    from pdf2image import convert_from_path  # type: ignore
    from PIL import Image  # type: ignore
    import pytesseract  # type: ignore
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False


def ocr_pdf(filepath: str, max_pages: int = 3, dpi: int = 200) -> str:
    """Render the first ``max_pages`` pages and run Tesseract OCR."""
    if not OCR_AVAILABLE:
        raise RuntimeError("OCR dependencies not available (pytesseract/pdf2image).")
    texts = []
    try:
        images = convert_from_path(filepath, dpi=dpi, first_page=1, last_page=max_pages)
        for img in images:
            try:
                texts.append(pytesseract.image_to_string(img))
            except Exception:
                continue
    except Exception as exc:
        logging.warning("OCR failed for %s: %s", filepath, exc)
    return "\n".join(texts).strip()


def extract_pdf_metadata_text(filepath: str, *, ocr_enabled: bool = False, ocr_pages: int = 3):
    """Return ``(metadata_dict, text_snippet)`` for a PDF file."""
    if PyPDF2 is None:
        return {}, ""
    meta: dict = {}
    snippet = ""
    try:
        with open(filepath, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            docinfo = reader.metadata
            if docinfo:
                try:
                    meta = {k[1:]: v for k, v in docinfo.items()}
                except Exception:
                    meta = {}
            texts = []
            for i, page in enumerate(reader.pages):
                if i >= 3:
                    break
                try:
                    texts.append(page.extract_text() or "")
                except Exception:
                    continue
            snippet = "\n".join(texts).strip()
            if (not snippet or len(snippet.strip()) < 50) and ocr_enabled and OCR_AVAILABLE:
                try:
                    ocr_text = ocr_pdf(filepath, max_pages=ocr_pages)
                    if ocr_text:
                        snippet = ocr_text
                        meta["ocr_used"] = True
                except Exception:
                    pass
    except Exception:
        pass
    return meta, snippet
