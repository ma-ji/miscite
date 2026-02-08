from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine.url import make_url

from server.miscite.core.config import Settings
from server.miscite.core.db import get_engine


ROOT_DIR = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT_DIR / "alembic.ini"
ALEMBIC_SCRIPT_DIR = ROOT_DIR / "migrations"


@dataclass(frozen=True)
class RevisionState:
    current_heads: tuple[str, ...]
    expected_heads: tuple[str, ...]

    @property
    def at_head(self) -> bool:
        return set(self.current_heads) == set(self.expected_heads) and bool(self.expected_heads)


def _alembic_config(settings: Settings) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_SCRIPT_DIR))
    cfg.set_main_option("sqlalchemy.url", settings.db_url)
    return cfg


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
    parent = os.path.dirname(database)
    if parent:
        os.makedirs(parent, exist_ok=True)


def expected_heads(settings: Settings) -> tuple[str, ...]:
    script = ScriptDirectory.from_config(_alembic_config(settings))
    return tuple(script.get_heads())


def current_heads(settings: Settings) -> tuple[str, ...]:
    engine = get_engine(settings)
    with engine.connect() as connection:
        ctx = MigrationContext.configure(connection)
        return tuple(ctx.get_current_heads())


def revision_state(settings: Settings) -> RevisionState:
    return RevisionState(
        current_heads=current_heads(settings),
        expected_heads=expected_heads(settings),
    )


def upgrade_to_head(settings: Settings) -> None:
    _ensure_db_parent_dir(settings.db_url)
    command.upgrade(_alembic_config(settings), "head")


def stamp_head(settings: Settings) -> None:
    _ensure_db_parent_dir(settings.db_url)
    command.stamp(_alembic_config(settings), "head")


def create_revision(settings: Settings, *, message: str, autogenerate: bool = True) -> None:
    command.revision(_alembic_config(settings), message=message, autogenerate=autogenerate)


def assert_db_current(settings: Settings) -> None:
    state = revision_state(settings)
    if state.at_head:
        return
    expected = ", ".join(state.expected_heads) if state.expected_heads else "none"
    current = ", ".join(state.current_heads) if state.current_heads else "none"
    raise RuntimeError(
        "Database schema revision mismatch. "
        f"current={current}, expected={expected}. "
        "Run `python -m server.migrate upgrade` before starting web/worker."
    )
