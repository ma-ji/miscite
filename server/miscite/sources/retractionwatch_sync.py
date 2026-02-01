from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from server.miscite.core.config import Settings


@dataclass(frozen=True)
class SyncResult:
    method: str
    updated: bool
    skipped_reason: str | None
    target_csv: str
    detail: dict


def sync_retractionwatch_dataset(settings: Settings, *, force: bool = False) -> SyncResult:
    target = settings.retractionwatch_csv
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = target.parent / ".retractionwatch_last_sync"

    lock_dir = target.parent.parent
    if not lock_dir.exists():
        lock_dir = target.parent
    with _file_lock(lock_dir / ".retractionwatch_sync.lock"):
        if not force and target.exists():
            freshness_path = stamp if stamp.exists() else target
            if _is_fresh(freshness_path, settings.rw_sync_interval_hours):
                return SyncResult(
                    method=settings.rw_sync_method,
                    updated=False,
                    skipped_reason="fresh",
                    target_csv=str(target),
                    detail={"age_hours": _age_hours(freshness_path)},
                )
        elif not force and stamp.exists() and _is_fresh(stamp, settings.rw_sync_interval_hours):
            return SyncResult(
                method=settings.rw_sync_method,
                updated=False,
                skipped_reason="fresh",
                target_csv=str(target),
                detail={"age_hours": _age_hours(stamp)},
            )

        method = settings.rw_sync_method
        if method == "git":
            detail = _sync_via_git(settings, target)
            _touch(stamp)
            return SyncResult(method="git", updated=True, skipped_reason=None, target_csv=str(target), detail=detail)

        if method == "http":
            detail = _sync_via_http(settings, target)
            _touch(stamp)
            return SyncResult(method="http", updated=True, skipped_reason=None, target_csv=str(target), detail=detail)

        raise ValueError(f"Unknown sync method: {method!r} (expected 'git' or 'http')")


def _sync_via_git(settings: Settings, target: Path) -> dict:
    repo_dir = settings.rw_git_dir
    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    if (repo_dir / ".git").exists():
        _run(["git", "-C", str(repo_dir), "pull", "--ff-only"])
    else:
        if repo_dir.exists() and any(repo_dir.iterdir()):
            raise RuntimeError(f"Refusing to clone into non-empty dir: {repo_dir}")
        _run(["git", "clone", "--depth", "1", settings.rw_git_repo, str(repo_dir)])

    source_csv = repo_dir / "retraction_watch.csv"
    if not source_csv.exists():
        raise RuntimeError(f"Could not find retraction_watch.csv in {repo_dir}")

    if source_csv.resolve() != target.resolve():
        _atomic_copy(source_csv, target)

    return {"repo": settings.rw_git_repo, "repo_dir": str(repo_dir), "source_csv": str(source_csv)}


def _sync_via_http(settings: Settings, target: Path) -> dict:
    url = settings.rw_http_url
    if not url:
        raise RuntimeError("MISCITE_RW_HTTP_URL is empty")

    headers = {"Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.8"}
    timeout = settings.api_timeout_seconds
    with requests.get(url, headers=headers, timeout=timeout, stream=True) as resp:
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(target.parent), prefix=".rw.", suffix=".tmp") as tmp:
            tmp_path = Path(tmp.name)
            try:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    tmp.write(chunk)
                tmp.flush()
                os.fsync(tmp.fileno())
            finally:
                tmp.close()
        tmp_path.replace(target)
    return {"url": url, "target_csv": str(target)}


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(dst.parent), prefix=".rw.", suffix=".tmp") as tmp:
        tmp_path = Path(tmp.name)
        tmp.close()
    try:
        shutil.copyfile(src, tmp_path)
        tmp_path.replace(dst)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp_path.unlink()


def _is_fresh(path: Path, interval_hours: int) -> bool:
    if interval_hours <= 0:
        return False
    if not path.exists():
        return False
    return _age_hours(path) < float(interval_hours)


def _age_hours(path: Path) -> float:
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return 1e9
    return max(0.0, (time.time() - mtime) / 3600.0)


@contextlib.contextmanager
def _file_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    import fcntl  # type: ignore

    f = lock_path.open("a+")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            f.close()
        except Exception:
            pass


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a"):
        os.utime(path, None)
