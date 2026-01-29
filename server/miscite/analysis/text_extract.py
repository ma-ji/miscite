from __future__ import annotations

from pathlib import Path

from server.miscite.analysis.docling_extract import extract_docling_text

def extract_text(path: Path) -> str:
    return extract_docling_text(path)
