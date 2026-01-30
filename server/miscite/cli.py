from __future__ import annotations

import argparse
import os
from pathlib import Path

_DEFAULT_BLANK_DB_PATH = Path("./data/miscite-blank.db").resolve()


def add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--blank-db",
        action="store_true",
        help="Use a blank sqlite DB at ./data/miscite-blank.db (overrides MISCITE_DB_URL).",
    )
    parser.add_argument(
        "--accelerator",
        choices=["cpu", "gpu"],
        help="Force CPU or GPU (CUDA) for local models.",
    )
    parser.add_argument(
        "--text-backend",
        choices=["markitdown", "docling"],
        help="Text extraction backend.",
    )


def apply_runtime_overrides(args: argparse.Namespace) -> None:
    if getattr(args, "text_backend", None):
        os.environ["MISCITE_TEXT_EXTRACT_BACKEND"] = args.text_backend
    if getattr(args, "accelerator", None):
        os.environ["MISCITE_ACCELERATOR"] = args.accelerator
    if getattr(args, "blank_db", False):
        _DEFAULT_BLANK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        if _DEFAULT_BLANK_DB_PATH.exists():
            _DEFAULT_BLANK_DB_PATH.unlink()
        os.environ["MISCITE_DB_URL"] = f"sqlite:///{_DEFAULT_BLANK_DB_PATH}"
