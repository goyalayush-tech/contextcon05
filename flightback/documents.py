"""Document intake: a PDF or an image becomes text page by page, then fact suggestions with page, quote and method.

  * A PDF page with a text layer is read directly (pypdf): exact text, no OCR guesswork.
  * A page with (almost) no text layer is a scan: it is rendered (pdftoppm) and OCR'd (tesseract).
  * PNG and JPEG images go straight to OCR.

Every page says how it was read, and OCR pages carry tesseract's mean word confidence. A low-confidence page is
flagged, because an OCR misread of a time or an amount changes the rights check. Suggestions still go through the
passenger-confirms step in the UI; nothing is applied silently.

The uploaded file is processed in a temporary directory and deleted. Only its name, size and SHA-256 travel on,
so the evidence index can name the exact document without the app keeping a copy of it.
"""
from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from .extract import suggest

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 20
MIN_TEXT_CHARS = 25        # fewer characters than this on a PDF page means "scanned": OCR it
OCR_DPI = 300
OCR_TIMEOUT_S = 60
LOW_CONFIDENCE = 70        # mean tesseract word confidence (0-100) below which a page is flagged

Runner = Callable[..., subprocess.CompletedProcess]


class DocumentError(ValueError):
    """A problem with the uploaded file that the passenger can fix. `status` is the HTTP status to report."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def sniff(data: bytes) -> Optional[str]:
    """Identify the file by its first bytes, not its name or the browser's content type."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    return None


def capabilities() -> dict:
    tess, ppm = shutil.which("tesseract"), shutil.which("pdftoppm")
    return {"text_layer": True, "ocr": bool(tess), "scanned_pdf": bool(tess and ppm),
            "max_bytes": MAX_BYTES, "max_pages": MAX_PAGES, "types": ["pdf", "png", "jpeg"],
            "detail": None if tess and ppm else
            ("OCR is not installed on this server (needs tesseract" + ("" if ppm else " and poppler's pdftoppm") +
             "). PDFs with a text layer still work; scans and photos cannot be read.")}


def parse_tsv(tsv: str) -> tuple[str, Optional[float]]:
    """Turn `tesseract ... tsv` output into line-broken text and the mean confidence of the recognised words."""
    lines: dict[tuple, list[str]] = {}
    confs: list[float] = []
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5":  # level 5 = word
            continue
        word = cols[11].strip()
        try:
            conf = float(cols[10])
        except ValueError:
            continue
        if not word or conf < 0:
            continue
        lines.setdefault((int(cols[1]), int(cols[2]), int(cols[3]), int(cols[4])), []).append(word)
        confs.append(conf)
    text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
    return text, (round(sum(confs) / len(confs), 1) if confs else None)


def ocr_image(path: Path, run: Runner = subprocess.run) -> tuple[str, Optional[float]]:
    tess = shutil.which("tesseract")
    if not tess:
        raise DocumentError("OCR is not installed on this server.", 503)
    try:
        p = run([tess, str(path), "stdout", "-l", "eng", "--psm", "3", "tsv"], capture_output=True, text=True,
                timeout=OCR_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise DocumentError(f"OCR took longer than {OCR_TIMEOUT_S}s on one page.", 422) from None
    if p.returncode != 0:
        raise DocumentError("OCR could not read this image.", 422)
    return parse_tsv(p.stdout)


def render_pdf_page(pdf: Path, page: int, outdir: Path, run: Runner = subprocess.run) -> Path:
    ppm = shutil.which("pdftoppm")
    if not ppm:
        raise DocumentError("Scanned PDF pages need poppler's pdftoppm, which is not installed.", 503)
    stem = outdir / f"p{page}"
    try:
        p = run([ppm, "-f", str(page), "-l", str(page), "-r", str(OCR_DPI), "-gray", "-png", "-singlefile",
                 str(pdf), str(stem)], capture_output=True, timeout=OCR_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise DocumentError(f"Rendering page {page} took longer than {OCR_TIMEOUT_S}s.", 422) from None
    out = stem.with_suffix(".png")
    if p.returncode != 0 or not out.exists():
        raise DocumentError(f"Page {page} of the PDF could not be rendered for OCR.", 422)
    return out


def pdf_text_pages(data: bytes) -> list[str]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentError("This PDF is password-protected. Remove the password and upload it again.")
        return [(pg.extract_text() or "") for pg in reader.pages]
    except DocumentError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as e:
        raise DocumentError(f"This file could not be read as a PDF ({type(e).__name__}).") from None


def read_document(name: str, data: bytes, run: Runner = subprocess.run) -> dict:
    """Return the document record and its pages: [{page, method, text, chars, confidence, note}]."""
    if not data:
        raise DocumentError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise DocumentError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.", 413)
    kind = sniff(data)
    if kind is None:
        raise DocumentError("Upload a PDF, PNG or JPEG. Other file types are not read.", 415)
    caps = capabilities()
    doc = {"name": name, "type": kind, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    pages: list[dict] = []
    notes: list[str] = []

    with tempfile.TemporaryDirectory(prefix="flightback-doc-") as tmp:
        tmpdir = Path(tmp)
        if kind == "pdf":
            texts = pdf_text_pages(data)
            doc["pages"] = len(texts)
            if len(texts) > MAX_PAGES:
                notes.append(f"Only the first {MAX_PAGES} of {len(texts)} pages were read.")
                texts = texts[:MAX_PAGES]
            src = tmpdir / "upload.pdf"
            src.write_bytes(data)
            for i, text in enumerate(texts, start=1):
                if len(text.strip()) >= MIN_TEXT_CHARS:
                    pages.append({"page": i, "method": "text_layer", "text": text, "confidence": None})
                elif not caps["scanned_pdf"]:
                    pages.append({"page": i, "method": "unread", "text": text, "confidence": None,
                                  "note": "Scanned page, and OCR is not installed on this server."})
                else:
                    img = render_pdf_page(src, i, tmpdir, run)
                    ocr_text, conf = ocr_image(img, run)
                    pages.append({"page": i, "method": "ocr", "text": ocr_text, "confidence": conf})
        else:
            doc["pages"] = 1
            if not caps["ocr"]:
                raise DocumentError("Photos and screenshots need OCR, which is not installed on this server. "
                                    "Upload a PDF with selectable text, or type the facts in.", 503)
            src = tmpdir / f"upload.{kind}"
            src.write_bytes(data)
            ocr_text, conf = ocr_image(src, run)
            pages.append({"page": 1, "method": "ocr", "text": ocr_text, "confidence": conf})

    for p in pages:
        p["chars"] = len(p["text"].strip())
        if p["method"] == "ocr" and p["chars"] == 0:
            p["note"] = "OCR found no text on this page."
        elif p["method"] == "ocr" and p["confidence"] is not None and p["confidence"] < LOW_CONFIDENCE:
            p["note"] = (f"Low OCR confidence ({p['confidence']:g}%). Check every value from this page against the "
                         "document; a misread digit changes the result.")
    return {"document": doc, "pages": pages, "notes": notes}


def suggest_from_document(name: str, data: bytes, run: Runner = subprocess.run) -> dict:
    """Read the document, then run the fact extractor on each page so every suggestion knows its page."""
    read = read_document(name, data, run)
    doc, candidates = read["document"], []
    notes = list(read["notes"])
    for p in read["pages"]:
        if p.get("note"):
            notes.append(f"Page {p['page']}: {p['note']}")
        if not p["text"].strip():
            continue
        s = suggest(p["text"])
        for c in s["candidates"]:
            c.update(page=p["page"], method=p["method"], confidence=p["confidence"],
                     low_confidence=p["method"] == "ocr" and p["confidence"] is not None
                     and p["confidence"] < LOW_CONFIDENCE)
            candidates.append(c)
        for n in s["notes"]:
            if not n.startswith("No dates") and n not in notes:
                notes.append(n)
    if not candidates:
        notes.append("No dates, amounts or reasons were recognised in this document. Enter the facts by hand.")
    methods = sorted({p["method"] for p in read["pages"]})
    return {"document": {**doc, "methods": methods},
            "pages": [{k: p.get(k) for k in ("page", "method", "chars", "confidence", "note")} | {"text": p["text"]}
                      for p in read["pages"]],
            "candidates": candidates, "notes": notes,
            "assumption": "Times without an offset are read as India time (IST). OCR can misread digits: confirm "
                          "each value against the document before using it."}
