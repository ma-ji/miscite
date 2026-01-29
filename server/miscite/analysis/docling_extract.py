from __future__ import annotations

from pathlib import Path


def extract_docling_text(path: Path) -> str:
    """Extract document markdown via Docling."""

    from docling.document_converter import DocumentConverter  # type: ignore

    converter = DocumentConverter()
    result = converter.convert(str(path))
    md = result.document.export_to_markdown()
    if not isinstance(md, str) or not md.strip():
        raise RuntimeError("Docling produced empty markdown.")
    return md
