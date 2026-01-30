from __future__ import annotations

import hashlib
import os
import pathlib
import shlex
import subprocess
import uuid
import zipfile
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile

from server.miscite.config import Settings


@dataclass(frozen=True)
class StoredUpload:
    storage_path: str
    sha256: str
    bytes_written: int


def _safe_filename(name: str) -> str:
    name = name.strip().replace("\\", "_").replace("/", "_")
    return name[:200] if name else "upload"


def _validate_docx_unpacked(path: pathlib.Path, *, max_unpacked_bytes: int) -> None:
    try:
        with zipfile.ZipFile(path) as zf:
            total = 0
            for info in zf.infolist():
                total += int(info.file_size or 0)
                if total > max_unpacked_bytes:
                    raise HTTPException(status_code=400, detail="DOCX file expands too large when unpacked.")
                if info.compress_size and info.file_size:
                    ratio = info.file_size / max(1, info.compress_size)
                    if ratio > 100.0:
                        raise HTTPException(status_code=400, detail="DOCX file compression ratio too high.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid DOCX file.") from e


def _scan_upload(path: pathlib.Path, *, settings: Settings) -> None:
    if not settings.upload_scan_enabled:
        return
    if not settings.upload_scan_command:
        raise HTTPException(status_code=500, detail="Upload scanning enabled but no scan command configured.")
    command = settings.upload_scan_command.format(path=str(path))
    try:
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            timeout=settings.upload_scan_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=400, detail="Upload scanning timed out.") from e
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail="File failed security scan.")


def save_upload(settings: Settings, upload: UploadFile) -> StoredUpload:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    ext = pathlib.Path(upload.filename or "").suffix.lower()
    if ext not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX are supported")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    digest = hashlib.sha256()
    bytes_written = 0

    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = settings.storage_dir / stored_name

    try:
        with open(dest, "wb") as f:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise HTTPException(status_code=413, detail="File too large")
                digest.update(chunk)
                f.write(chunk)
        if ext == ".docx":
            _validate_docx_unpacked(dest, max_unpacked_bytes=settings.max_unpacked_mb * 1024 * 1024)
        _scan_upload(dest, settings=settings)
    except HTTPException:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise

    return StoredUpload(storage_path=str(dest), sha256=digest.hexdigest(), bytes_written=bytes_written)
