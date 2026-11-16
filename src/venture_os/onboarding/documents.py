"""Extract plain text from uploaded founder documents. Uploads are untrusted: nothing is executed,
only text is read, and size and type are limited."""

from __future__ import annotations

import io
from pathlib import PurePath

MAX_BYTES = 10 * 1024 * 1024
MAX_CHARS = 200_000
ALLOWED = {".pdf", ".docx", ".txt", ".md"}


class DocumentError(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext not in ALLOWED:
        raise DocumentError(f"Unsupported file type {ext or '(none)'}; use PDF, Word (.docx), .txt or .md")
    if len(data) > MAX_BYTES:
        raise DocumentError("File is larger than 10 MB")
    if ext in (".txt", ".md"):
        text = data.decode("utf-8", errors="replace")
    elif ext == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:
            raise DocumentError(f"Could not read PDF: {e}") from e
    else:
        from docx import Document

        try:
            doc = Document(io.BytesIO(data))
        except Exception as e:
            raise DocumentError(f"Could not read Word file: {e}") from e
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        text = "\n".join(parts)
    text = text.replace("\x00", "").strip()
    if not text:
        raise DocumentError("No readable text found (scanned PDFs need OCR, which is not supported yet)")
    return text[:MAX_CHARS]
