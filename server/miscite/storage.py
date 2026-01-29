from __future__ import annotations

import hashlib
import os
import pathlib
import uuid
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
    except HTTPException:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise

    return StoredUpload(storage_path=str(dest), sha256=digest.hexdigest(), bytes_written=bytes_written)

