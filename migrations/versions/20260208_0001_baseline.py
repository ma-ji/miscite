"""Baseline schema from SQLAlchemy models.

Revision ID: 20260208_0001
Revises:
Create Date: 2026-02-08 00:00:00
"""
from __future__ import annotations

from alembic import op

from server.miscite.core import models  # noqa: F401
from server.miscite.core.db import Base

# revision identifiers, used by Alembic.
revision = "20260208_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
