from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from server.miscite.core.config import Settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=8)
def _engine_for(db_url: str):
    connect_args = {}
    _ensure_db_parent_dir(db_url)
    if db_url.startswith("sqlite:"):
        connect_args = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
    _configure_sqlite(engine, db_url)
    return engine


def get_engine(settings: Settings):
    return _engine_for(settings.db_url)


def get_sessionmaker(settings: Settings):
    return _sessionmaker_for(settings.db_url)


@lru_cache(maxsize=8)
def _sessionmaker_for(db_url: str):
    engine = _engine_for(db_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(settings: Settings) -> None:
    from server.miscite.core import models  # noqa: F401

    _ensure_db_parent_dir(settings.db_url)
    engine = get_engine(settings)
    Base.metadata.create_all(engine)


def _ensure_db_parent_dir(db_url: str) -> None:
    try:
        url = make_url(db_url)
    except Exception:
        return
    if url.drivername != "sqlite":
        return
    database = url.database
    if not database or database == ":memory:":
        return
    import os

    parent = os.path.dirname(database)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _configure_sqlite(engine, db_url: str) -> None:
    if not db_url.startswith("sqlite:"):
        return
    file_based = False
    try:
        url = make_url(db_url)
        file_based = bool(url.database) and url.database != ":memory:"
    except Exception:
        file_based = False

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            if file_based:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


@contextmanager
def session_scope(settings: Settings) -> Generator[Session, None, None]:
    SessionLocal = get_sessionmaker(settings)
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def db_session(request: Request) -> Generator[Session, None, None]:
    settings: Settings = request.app.state.settings
    SessionLocal = get_sessionmaker(settings)
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
