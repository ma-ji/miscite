from __future__ import annotations

"""Helper script to export Zotero file attachments to Markdown.

This wraps the :mod:`zotero_files2md` library using the same settings model
as documented in the upstream README, but wires configuration through
environment variables so it can be run from this project with ``.env``.

Relevant environment variables
------------------------------
Required:
- ZOTERO_API_KEY        – Zotero Web API key
- ZOTERO_LIBRARY_ID     – Library ID (numeric) for user or group library
- ZOTERO_LIBRARY_TYPE   – "user" or "group"

Optional (sensible defaults are provided):
- ZOTERO_OUTPUT_DIR     – Output directory for Markdown (required for non-batch)
- ZOTERO_COLLECTIONS    – Comma/newline-separated collection keys to filter on
- ZOTERO_COLLECTION_OUTPUTS – Comma/newline-separated ``KEY=DIR`` pairs for batch export
  Example: ``ZOTERO_COLLECTION_OUTPUTS=X5FACDN2=../kb/theory,EH43AXY6=../kb/local_facts``
- ZOTERO_TAGS           – Comma/newline-separated tag names to filter on
- ZOTERO_OVERWRITE      – "true"/"false" (default "false")
- ZOTERO_DRY_RUN        – "true"/"false" (default "false")
- ZOTERO_LIMIT          – Positive integer; max attachments to process
- ZOTERO_CHUNK_SIZE     – Positive integer; API page size (default "100")
- ZOTERO_MAX_WORKERS    – Positive integer; overrides worker auto-detection
- ZOTERO_FORCE_FULL_PAGE_OCR     – "true"/"false" (default "false")
- ZOTERO_DO_PICTURE_DESCRIPTION  – "true"/"false" (default "false")
- ZOTERO_IMAGE_RESOLUTION_SCALE  – Float (default "4.0")
- ZOTERO_USE_MULTI_GPU           – "true"/"false" (default "true")
"""

import os
from pathlib import Path

import dotenv
from zotero_files2md import export_collections, export_library
from zotero_files2md.settings import ExportSettings, parse_collection_output_pairs


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _split_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    raw = value.strip()
    if not raw:
        return []
    parts = raw.replace("\n", ",").split(",")
    return [part.strip() for part in parts if part.strip()]


def _parse_positive_int(value: str | None, *, name: str) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _parse_positive_float(value: str | None, *, name: str) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive number")
    return parsed


def build_settings(*, output_dir: Path, collections: set[str]) -> ExportSettings:
    """Build :class:`ExportSettings` from environment variables.

    This mirrors the programmatic usage example in the zotero-files2md
    README.
    """

    api_key = os.getenv("ZOTERO_API_KEY")
    library_id = os.getenv("ZOTERO_LIBRARY_ID")
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE")

    if not api_key:
        raise RuntimeError("ZOTERO_API_KEY must be set in the environment or .env file")

    if not library_id:
        raise RuntimeError("ZOTERO_LIBRARY_ID must be set in the environment or .env file")

    if not library_type:
        raise RuntimeError(
            "ZOTERO_LIBRARY_TYPE must be set to 'user' or 'group' in the environment or .env file",
        )

    tags_env = os.getenv("ZOTERO_TAGS")
    tags = set(_split_env_list(tags_env))

    overwrite = _parse_bool(os.getenv("ZOTERO_OVERWRITE"), default=False)
    dry_run = _parse_bool(os.getenv("ZOTERO_DRY_RUN"), default=False)

    chunk_size = _parse_positive_int(os.getenv("ZOTERO_CHUNK_SIZE"), name="ZOTERO_CHUNK_SIZE")
    max_workers = _parse_positive_int(os.getenv("ZOTERO_MAX_WORKERS"), name="ZOTERO_MAX_WORKERS")
    limit = _parse_positive_int(os.getenv("ZOTERO_LIMIT"), name="ZOTERO_LIMIT")

    force_full_page_ocr = _parse_bool(os.getenv("ZOTERO_FORCE_FULL_PAGE_OCR"), default=False)
    do_picture_description = _parse_bool(os.getenv("ZOTERO_DO_PICTURE_DESCRIPTION"), default=False)
    image_resolution_scale = _parse_positive_float(
        os.getenv("ZOTERO_IMAGE_RESOLUTION_SCALE"),
        name="ZOTERO_IMAGE_RESOLUTION_SCALE",
    )
    use_multi_gpu = _parse_bool(os.getenv("ZOTERO_USE_MULTI_GPU"), default=True)

    return ExportSettings.from_cli_args(
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,  # validated by ExportSettings
        output_dir=output_dir,
        collections=sorted(collections),
        tags=sorted(tags),
        overwrite=overwrite,
        dry_run=dry_run,
        limit=limit,
        chunk_size=chunk_size or 100,
        max_workers=max_workers,
        force_full_page_ocr=force_full_page_ocr,
        do_picture_description=do_picture_description,
        image_resolution_scale=image_resolution_scale or 4.0,
        use_multi_gpu=use_multi_gpu,
        image_processing="placeholder",
    )


def main() -> None:
    dotenv.load_dotenv()

    collection_output_values = _split_env_list(os.getenv("ZOTERO_COLLECTION_OUTPUTS"))
    collection_output_dirs = (
        parse_collection_output_pairs(collection_output_values)
        if collection_output_values
        else {}
    )

    if collection_output_dirs:
        base_output_dir = os.getenv("ZOTERO_OUTPUT_DIR")
        if base_output_dir:
            output_dir = Path(base_output_dir)
        else:
            output_dir = next(iter(collection_output_dirs.values()))
        settings = build_settings(output_dir=output_dir, collections=set())
        summary = export_collections(settings, collection_output_dirs)
        print(summary)
        return

    output_dir_env = os.getenv("ZOTERO_OUTPUT_DIR")
    if not output_dir_env:
        raise RuntimeError(
            "ZOTERO_OUTPUT_DIR must be set for non-batch exports (set ZOTERO_COLLECTION_OUTPUTS for batch mode).",
        )

    collections = set(_split_env_list(os.getenv("ZOTERO_COLLECTIONS")))
    settings = build_settings(output_dir=Path(output_dir_env), collections=collections)
    summary = export_library(settings)
    print(summary)


if __name__ == "__main__":
    main()
