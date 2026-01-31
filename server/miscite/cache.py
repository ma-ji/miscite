from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import delete

from server.miscite.config import Settings
from server.miscite.db import get_sessionmaker
from server.miscite.models import CacheEntry

_CACHE_SCHEMA_VERSION = 1


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _sha256_hex(parts: Sequence[str]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


@dataclass(frozen=True)
class Cache:
    settings: Settings
    scope: str = "global"

    def scoped(self, scope: str) -> "Cache":
        scope = (scope or "").strip() or "global"
        if scope == self.scope:
            return self
        return Cache(settings=self.settings, scope=scope)

    def _key(self, namespace: str, parts: Sequence[str]) -> str:
        return _sha256_hex([str(_CACHE_SCHEMA_VERSION), self.scope, namespace, *[str(p) for p in parts]])

    def get_json(self, namespace: str, parts: Sequence[str]) -> tuple[bool, Any]:
        if not self.settings.cache_enabled:
            return False, None
        key = self._key(namespace, parts)
        SessionLocal = get_sessionmaker(self.settings)
        db = SessionLocal()
        try:
            entry = db.get(CacheEntry, key)
            if not entry:
                return False, None
            if entry.expires_at < _utcnow():
                db.delete(entry)
                db.commit()
                return False, None
            if entry.value_json is None:
                return False, None
            return True, json.loads(entry.value_json)
        except Exception:
            return False, None
        finally:
            db.close()

    def set_json(self, namespace: str, parts: Sequence[str], value: Any, *, ttl_seconds: float) -> None:
        if not self.settings.cache_enabled:
            return
        key = self._key(namespace, parts)
        SessionLocal = get_sessionmaker(self.settings)
        db = SessionLocal()
        try:
            expires_at = _utcnow() + dt.timedelta(seconds=float(ttl_seconds))
            entry = CacheEntry(
                key=key,
                namespace=namespace,
                scope=self.scope,
                created_at=_utcnow(),
                expires_at=expires_at,
                value_json=json.dumps(value, ensure_ascii=False),
            )
            db.merge(entry)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def reap_expired(self) -> int:
        if not self.settings.cache_enabled:
            return 0
        SessionLocal = get_sessionmaker(self.settings)
        db = SessionLocal()
        try:
            now = _utcnow()
            result = db.execute(delete(CacheEntry).where(CacheEntry.expires_at < now))
            db.commit()
            return int(result.rowcount or 0)
        except Exception:
            db.rollback()
            return 0
        finally:
            db.close()

    # -------------------------
    # File-backed helpers
    # -------------------------

    def get_text_file(self, namespace: str, parts: Sequence[str], *, ttl_days: int) -> tuple[bool, str]:
        if not self.settings.cache_enabled:
            return False, ""
        path = self._file_path(namespace, parts, ext="txt")
        try:
            st = path.stat()
        except FileNotFoundError:
            return False, ""
        except Exception:
            return False, ""

        ttl_seconds = float(ttl_days) * 86400.0
        if ttl_seconds > 0 and (dt.datetime.now(dt.UTC).timestamp() - st.st_mtime) > ttl_seconds:
            try:
                path.unlink()
            except OSError:
                pass
            return False, ""

        try:
            return True, path.read_text(encoding="utf-8")
        except Exception:
            return False, ""

    def set_text_file(self, namespace: str, parts: Sequence[str], value: str) -> None:
        if not self.settings.cache_enabled:
            return
        path = self._file_path(namespace, parts, ext="txt")
        tmp: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".tmp.{os.getpid()}")
            tmp.write_text(value, encoding="utf-8")
            tmp.replace(path)
        except Exception:
            try:
                if tmp is not None:
                    tmp.unlink()
            except OSError:
                pass

    def _file_path(self, namespace: str, parts: Sequence[str], *, ext: str) -> Path:
        key = self._key(f"{namespace}:file", parts)
        safe_ns = "".join(ch for ch in namespace if ch.isalnum() or ch in {"_", "-", "."})[:80] or "cache"
        return Path(self.settings.cache_dir) / safe_ns / f"{key}.{ext}"
