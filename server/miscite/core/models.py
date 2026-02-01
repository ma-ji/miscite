from __future__ import annotations

import datetime as dt
import uuid
from enum import Enum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.miscite.core.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class JobStatus(str, Enum):
    pending = "PENDING"
    running = "RUNNING"
    failed = "FAILED"
    canceled = "CANCELED"
    completed = "COMPLETED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.now(dt.UTC))

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user")
    jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="user")
    billing: Mapped["BillingAccount | None"] = relationship(back_populates="user")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.now(dt.UTC))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)

    user: Mapped["User"] = relationship(back_populates="sessions")


class LoginCode(Base):
    __tablename__ = "login_codes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.now(dt.UTC))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(127))
    storage_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.now(dt.UTC))


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    document_id: Mapped[str] = mapped_column(String(32), ForeignKey("documents.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.pending.value, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.now(dt.UTC))
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_heartbeat_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    methodology_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_version: Mapped[str] = mapped_column(String(32), default="0.1")
    access_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    access_token_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    access_token_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="jobs")


class AnalysisJobEvent(Base):
    __tablename__ = "analysis_job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("analysis_jobs.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.now(dt.UTC), index=True)
    stage: Mapped[str] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)


class BillingAccount(Base):
    __tablename__ = "billing_accounts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), unique=True, index=True)

    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subscription_status: Mapped[str] = mapped_column(String(32), default="inactive", index=True)
    current_period_end: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.now(dt.UTC))

    user: Mapped["User"] = relationship(back_populates="billing")


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(96), index=True)
    scope: Mapped[str] = mapped_column(String(96), index=True, default="global")

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.now(dt.UTC))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)

    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
