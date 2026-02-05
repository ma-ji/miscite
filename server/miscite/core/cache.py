from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import delete

from server.miscite.core.config import Settings
from server.miscite.core.db import get_sessionmaker
from server.miscite.core.models import CacheEntry

_CACHE_SCHEMA_VERSION = 1
logger = logging.getLogger("miscite.cache")


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _as_utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


def _sha256_hex(parts: Sequence[str]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


@dataclass
class CacheDebugStats:
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _totals: Counter[str] = field(default_factory=Counter, init=False, repr=False)
    _by_namespace: dict[str, Counter[str]] = field(default_factory=dict, init=False, repr=False)

    def increment(self, namespace: str, metric: str) -> None:
        namespace = (namespace or "").strip() or "unknown"
        metric = (metric or "").strip()
        if not metric:
            return
        with self._lock:
            self._totals[metric] += 1
            ns = self._by_namespace.get(namespace)
            if ns is None:
                ns = Counter()
                self._by_namespace[namespace] = ns
            ns[metric] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            totals = dict(sorted(self._totals.items()))
            namespaces = {
                namespace: dict(sorted(counter.items()))
                for namespace, counter in sorted(self._by_namespace.items())
            }
        return {"totals": totals, "namespaces": namespaces}


@dataclass(frozen=True)
class Cache:
    settings: Settings
    scope: str = "global"
    debug_stats: CacheDebugStats = field(default_factory=CacheDebugStats, repr=False, compare=False)

    def scoped(self, scope: str) -> "Cache":
        scope = (scope or "").strip() or "global"
        if scope == self.scope:
            return self
        return Cache(settings=self.settings, scope=scope, debug_stats=self.debug_stats)

    def _key(self, namespace: str, parts: Sequence[str]) -> str:
        return _sha256_hex([str(_CACHE_SCHEMA_VERSION), self.scope, namespace, *[str(p) for p in parts]])

    def _debug_log_each(self) -> bool:
        return bool(
            self.settings.cache_enabled
            and getattr(self.settings, "cache_debug_log_each", False)
            and logger.isEnabledFor(logging.DEBUG)
        )

    def _debug_hint(self, namespace: str, parts: Sequence[str]) -> str | None:
        ns = (namespace or "").strip().lower()
        if not ns or ns.startswith("openrouter."):
            return None

        if ns == "openalex.work_by_id" and parts:
            return f"id={str(parts[0]).strip()}"
        if ns == "openalex.work_by_doi" and parts:
            return f"doi={str(parts[0]).strip()}"
        if ns == "openalex.list_citing_works" and parts:
            suffix = str(parts[0]).strip()
            rows = str(parts[1]).strip() if len(parts) > 1 else ""
            return f"id={suffix} rows={rows}".strip()
        if ns == "openalex.search" and parts:
            q = " ".join(str(parts[0]).split())
            if len(q) > 120:
                q = q[:120] + "…"
            rows = str(parts[1]).strip() if len(parts) > 1 else ""
            return f"q={q} rows={rows}".strip()

        return None

    def get_json(self, namespace: str, parts: Sequence[str]) -> tuple[bool, Any]:
        if not self.settings.cache_enabled:
            return False, None
        key = self._key(namespace, parts)
        SessionLocal = get_sessionmaker(self.settings)
        db = SessionLocal()
        try:
            entry = db.get(CacheEntry, key)
            if not entry:
                self.debug_stats.increment(namespace, "json_get_miss")
                if self._debug_log_each():
                    hint = self._debug_hint(namespace, parts)
                    logger.debug(
                        "cache json_get MISS ns=%s scope=%s key=%s%s",
                        namespace,
                        self.scope,
                        key[:12],
                        f" {hint}" if hint else "",
                    )
                return False, None
            expires_at = _as_utc(entry.expires_at)
            if expires_at is None or expires_at < _utcnow():
                db.delete(entry)
                db.commit()
                self.debug_stats.increment(namespace, "json_get_miss")
                if self._debug_log_each():
                    hint = self._debug_hint(namespace, parts)
                    logger.debug(
                        "cache json_get EXPIRED ns=%s scope=%s key=%s%s",
                        namespace,
                        self.scope,
                        key[:12],
                        f" {hint}" if hint else "",
                    )
                return False, None
            if entry.value_json is None:
                self.debug_stats.increment(namespace, "json_get_miss")
                if self._debug_log_each():
                    hint = self._debug_hint(namespace, parts)
                    logger.debug(
                        "cache json_get EMPTY ns=%s scope=%s key=%s%s",
                        namespace,
                        self.scope,
                        key[:12],
                        f" {hint}" if hint else "",
                    )
                return False, None
            self.debug_stats.increment(namespace, "json_get_hit")
            if self._debug_log_each():
                hint = self._debug_hint(namespace, parts)
                logger.debug(
                    "cache json_get HIT ns=%s scope=%s key=%s%s",
                    namespace,
                    self.scope,
                    key[:12],
                    f" {hint}" if hint else "",
                )
            return True, json.loads(entry.value_json)
        except Exception:
            self.debug_stats.increment(namespace, "json_get_error")
            if self._debug_log_each():
                hint = self._debug_hint(namespace, parts)
                logger.debug(
                    "cache json_get ERROR ns=%s scope=%s key=%s%s",
                    namespace,
                    self.scope,
                    key[:12],
                    f" {hint}" if hint else "",
                )
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
            self.debug_stats.increment(namespace, "json_set_ok")
        except Exception:
            db.rollback()
            self.debug_stats.increment(namespace, "json_set_error")
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
        key_short = path.stem[:12]
        try:
            st = path.stat()
        except FileNotFoundError:
            self.debug_stats.increment(namespace, "file_get_miss")
            if self._debug_log_each():
                hint = self._debug_hint(namespace, parts)
                logger.debug(
                    "cache file_get MISS ns=%s scope=%s key=%s%s",
                    namespace,
                    self.scope,
                    key_short,
                    f" {hint}" if hint else "",
                )
            return False, ""
        except Exception:
            self.debug_stats.increment(namespace, "file_get_error")
            if self._debug_log_each():
                hint = self._debug_hint(namespace, parts)
                logger.debug(
                    "cache file_get ERROR ns=%s scope=%s key=%s%s",
                    namespace,
                    self.scope,
                    key_short,
                    f" {hint}" if hint else "",
                )
            return False, ""

        ttl_seconds = float(ttl_days) * 86400.0
        if ttl_seconds > 0 and (dt.datetime.now(dt.UTC).timestamp() - st.st_mtime) > ttl_seconds:
            try:
                path.unlink()
            except OSError:
                pass
            self.debug_stats.increment(namespace, "file_get_expired")
            if self._debug_log_each():
                hint = self._debug_hint(namespace, parts)
                logger.debug(
                    "cache file_get EXPIRED ns=%s scope=%s key=%s%s",
                    namespace,
                    self.scope,
                    key_short,
                    f" {hint}" if hint else "",
                )
            return False, ""

        try:
            self.debug_stats.increment(namespace, "file_get_hit")
            if self._debug_log_each():
                hint = self._debug_hint(namespace, parts)
                logger.debug(
                    "cache file_get HIT ns=%s scope=%s key=%s%s",
                    namespace,
                    self.scope,
                    key_short,
                    f" {hint}" if hint else "",
                )
            return True, path.read_text(encoding="utf-8")
        except Exception:
            self.debug_stats.increment(namespace, "file_get_error")
            if self._debug_log_each():
                hint = self._debug_hint(namespace, parts)
                logger.debug(
                    "cache file_get ERROR ns=%s scope=%s key=%s%s",
                    namespace,
                    self.scope,
                    key_short,
                    f" {hint}" if hint else "",
                )
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
            self.debug_stats.increment(namespace, "file_set_ok")
        except Exception:
            self.debug_stats.increment(namespace, "file_set_error")
            try:
                if tmp is not None:
                    tmp.unlink()
            except OSError:
                pass

    def debug_snapshot(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.settings.cache_enabled),
            "scope": self.scope,
            **self.debug_stats.snapshot(),
        }

    def _file_path(self, namespace: str, parts: Sequence[str], *, ext: str) -> Path:
        key = self._key(f"{namespace}:file", parts)
        safe_ns = "".join(ch for ch in namespace if ch.isalnum() or ch in {"_", "-", "."})[:80] or "cache"
        return Path(self.settings.cache_dir) / safe_ns / f"{key}.{ext}"
