from __future__ import annotations

import multiprocessing as mp
from pathlib import Path
from queue import Empty


def _extract_text_direct(path: Path, *, backend: str) -> str:
    backend = backend.strip().lower()
    if backend == "docling":
        from server.miscite.analysis.docling_extract import extract_docling_text

        return extract_docling_text(path)
    if backend == "markitdown":
        from server.miscite.analysis.markitdown_extract import extract_markitdown_text

        return extract_markitdown_text(path)
    raise ValueError(f"Unsupported text extraction backend: {backend!r}")


def _extract_worker(path_str: str, backend: str, queue: mp.Queue) -> None:
    try:
        text = _extract_text_direct(Path(path_str), backend=backend)
        queue.put(("ok", text))
    except Exception as exc:
        queue.put(("err", str(exc)))


def extract_text(
    path: Path,
    *,
    backend: str,
    timeout_seconds: float = 120.0,
    use_subprocess: bool = True,
) -> str:
    if not use_subprocess:
        return _extract_text_direct(path, backend=backend)

    queue: mp.Queue = mp.Queue()
    proc = mp.get_context("spawn").Process(
        target=_extract_worker,
        args=(str(path), backend, queue),
        daemon=True,
    )
    proc.start()
    proc.join(timeout_seconds)
    if proc.is_alive():
        proc.terminate()
        proc.join(2.0)
        raise RuntimeError("Text extraction timed out.")

    try:
        status, payload = queue.get_nowait()
    except Empty:
        raise RuntimeError("Text extraction failed with no output.")
    if status == "ok":
        return payload
    raise RuntimeError(f"Text extraction failed: {payload}")
