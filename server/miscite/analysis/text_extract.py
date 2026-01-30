from __future__ import annotations

import multiprocessing as mp
import time
from multiprocessing.connection import Connection
from pathlib import Path


def _extract_text_direct(path: Path, *, backend: str) -> str:
    backend = backend.strip().lower()
    if backend == "docling":
        from server.miscite.analysis.docling_extract import extract_docling_text

        return extract_docling_text(path)
    if backend == "markitdown":
        from server.miscite.analysis.markitdown_extract import extract_markitdown_text

        return extract_markitdown_text(path)
    raise ValueError(f"Unsupported text extraction backend: {backend!r}")


def _extract_worker(path_str: str, backend: str, conn: Connection) -> None:
    try:
        text = _extract_text_direct(Path(path_str), backend=backend)
        conn.send(("ok", text))
    except Exception as exc:
        conn.send(("err", f"{type(exc).__name__}: {exc}"))
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _stop_process(proc: mp.Process) -> None:
    if not proc.is_alive():
        return
    proc.terminate()
    proc.join(2.0)
    if proc.is_alive() and hasattr(proc, "kill"):
        proc.kill()
        proc.join(2.0)


def extract_text(
    path: Path,
    *,
    backend: str,
    timeout_seconds: float = 120.0,
    use_subprocess: bool = True,
    process_context: str = "spawn",
) -> str:
    if not use_subprocess:
        return _extract_text_direct(path, backend=backend)

    ctx = mp.get_context(process_context)
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_extract_worker,
        args=(str(path), backend, child_conn),
        daemon=False,
    )
    proc.start()
    child_conn.close()

    deadline = time.monotonic() + float(timeout_seconds)
    poll_interval = 0.25
    status: str | None = None
    payload: str | None = None
    timed_out = False
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            if parent_conn.poll(min(poll_interval, remaining)):
                status, payload = parent_conn.recv()
                break
            if not proc.is_alive():
                break
    finally:
        try:
            parent_conn.close()
        except Exception:
            pass

    if timed_out:
        _stop_process(proc)
        raise RuntimeError(
            "Text extraction timed out "
            f"(timeout={timeout_seconds}s, backend={backend!r}, process_context={process_context!r})."
        )

    if status is None or payload is None:
        exitcode = proc.exitcode
        _stop_process(proc)
        proc.join(2.0)
        raise RuntimeError(f"Text extraction failed with no output (exitcode={exitcode}).")

    _stop_process(proc)
    proc.join(2.0)

    if status == "ok":
        return payload
    raise RuntimeError(f"Text extraction failed: {payload}")
