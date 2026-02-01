from __future__ import annotations

from pathlib import Path


def extract_markitdown_text(path: Path) -> str:
    """Extract document text via MarkItDown."""
    try:
        from markitdown import MarkItDown  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("MarkItDown is required for text extraction (pip install 'markitdown[all]').") from e

    converter = MarkItDown()
    result = converter.convert(str(path))
    text = getattr(result, "text_content", None)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("MarkItDown produced empty text.")
    return text
