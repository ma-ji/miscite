from __future__ import annotations


def normalize_predatory_name(value: str) -> str:
    cleaned = "".join(ch.lower() for ch in value.strip() if ch.isalnum() or ch.isspace())
    return " ".join(cleaned.split())


def normalize_issn(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("-", "").strip().lower()
