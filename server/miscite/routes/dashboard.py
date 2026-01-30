from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from server.miscite.config import Settings
from server.miscite.db import db_session, get_sessionmaker
from server.miscite.models import AnalysisJob, AnalysisJobEvent, BillingAccount, Document, JobStatus, User
from server.miscite.rate_limit import acquire_stream_slot, enforce_rate_limit, release_stream_slot
from server.miscite.security import access_token_hint, generate_access_token, hash_token, require_csrf, require_user
from server.miscite.storage import save_upload
from server.miscite.web import template_context, templates

router = APIRouter()


def _subscription_active(account: BillingAccount | None) -> bool:
    if account is None:
        return False
    return account.subscription_status in {"active", "trialing"}


def _human_date(ts: dt.datetime | None) -> str:
    if ts is None:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.UTC)
    return f"{ts.strftime('%b')} {ts.day}, {ts.year}"


def _human_datetime(ts: dt.datetime | None) -> str:
    if ts is None:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.UTC)
    return f"{ts.strftime('%b')} {ts.day}, {ts.year} at {ts.strftime('%H:%M')} UTC"


def _relative_time(ts: dt.datetime | None) -> str:
    if ts is None:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.UTC)
    now = dt.datetime.now(dt.UTC)
    delta = now - ts
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 86400 * 7:
        return f"{seconds // 86400}d ago"
    if seconds < 86400 * 30:
        return f"{max(1, seconds // (86400 * 7))}w ago"
    if seconds < 86400 * 365:
        return f"{max(1, seconds // (86400 * 30))}mo ago"
    return f"{max(1, seconds // (86400 * 365))}y ago"


def _safe_error_message(settings: Settings, message: str | None) -> str | None:
    if not message:
        return None
    if settings.expose_sensitive_report_fields:
        return message
    return "Analysis failed. Please retry or contact support."


def _load_report(job: AnalysisJob) -> dict | None:
    if not job.report_json:
        return None
    try:
        return json.loads(job.report_json)
    except Exception:
        return None


def _token_expired(job: AnalysisJob) -> bool:
    if job.access_token_hash and job.access_token_expires_at is None:
        return True
    if job.access_token_expires_at and job.access_token_expires_at < dt.datetime.now(dt.UTC):
        return True
    return False


def _resolve_access_token(
    db: Session,
    token_value: str,
) -> tuple[tuple[AnalysisJob, Document] | None, str | None]:
    token_value = token_value.strip()
    if not token_value:
        return None, "Please enter an access token."

    token_hash = hash_token(token_value)
    row = db.execute(
        select(AnalysisJob, Document)
        .join(Document, Document.id == AnalysisJob.document_id)
        .where(AnalysisJob.access_token_hash == token_hash)
        .limit(1)
    ).first()
    if not row:
        return None, "That token was not recognized. Double-check and try again."

    job, doc = row
    now = dt.datetime.now(dt.UTC)
    if job.access_token_expires_at is None or job.access_token_expires_at < now:
        return None, "That token has expired. Request a new token from the report owner."
    return (job, doc), None


_PATH_HINT_RE = re.compile(r"(^/|[A-Za-z]:\\|\\.\\./|/data/|/home/)")
_URL_HINT_RE = re.compile(r"^https?://", re.IGNORECASE)


def _looks_sensitive(detail: str) -> bool:
    if not detail:
        return False
    if _PATH_HINT_RE.search(detail):
        return True
    if _URL_HINT_RE.search(detail):
        return True
    return False


def _redact_sources(sources: list[dict] | None) -> list[dict] | None:
    if not sources:
        return sources
    redacted: list[dict] = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        name = str(src.get("name") or "").strip() or "Source"
        detail = str(src.get("detail") or "").strip()
        if "dataset" in name.lower() or "api" in name.lower() or _looks_sensitive(detail):
            detail = "Available on request."
        redacted.append({"name": name, "detail": detail})
    return redacted


def _redact_methodology(md: str | None) -> str | None:
    if not md:
        return md
    lines = md.splitlines()
    out: list[str] = []
    skip = False
    for line in lines:
        header = line.strip().lower()
        if header.startswith("## data sources used") or header.startswith("## configuration snapshot"):
            skip = True
            continue
        if skip:
            if header.startswith("## "):
                skip = False
            else:
                continue
        if skip:
            continue
        out.append(line)
    return "\n".join(out).strip() or None


@router.get("/")
def root(request: Request, db: Session = Depends(db_session)):
    user = None
    try:
        user = require_user(request, db)
    except HTTPException:
        user = None
    if user:
        request.state.user = user
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        "home.html",
        template_context(request, title="Audit-ready citation checks"),
    )


@router.get("/reports/access")
def report_access_form(request: Request):
    return templates.TemplateResponse(
        "report_access.html",
        template_context(request, title="Get report"),
    )


@router.post("/reports/access")
def report_access(request: Request, token: str = Form(""), db: Session = Depends(db_session)):
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="report-access",
        limit=settings.rate_limit_report_access,
        window_seconds=settings.rate_limit_window_seconds,
    )
    token_value = token.strip()
    resolved, error = _resolve_access_token(db, token_value)
    if error:
        return templates.TemplateResponse(
            "report_access.html",
            template_context(
                request,
                title="Get report",
                access_error=error,
            ),
        )
    return RedirectResponse(f"/reports/{token_value}", status_code=303)


@router.get("/reports/{token}")
def report_access_token(request: Request, token: str, db: Session = Depends(db_session)):
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="report-access",
        limit=settings.rate_limit_report_access,
        window_seconds=settings.rate_limit_window_seconds,
    )
    token_value = token.strip()
    resolved, error = _resolve_access_token(db, token_value)
    if error:
        return templates.TemplateResponse(
            "report_access.html",
            template_context(
                request,
                title="Get report",
                access_error=error,
            ),
        )

    job, doc = resolved
    report = _load_report(job)

    return templates.TemplateResponse(
        "job.html",
        template_context(
            request,
            title="Report",
            job={
                "id": job.id,
                "status": job.status,
                "filename": doc.original_filename,
                "error_message": None,
                "has_error": bool(job.error_message),
                "access_token_hint": job.access_token_hint,
            },
            report=report,
            report_token=token_value,
            methodology_md="",
            public_view=True,
            hide_report_access=True,
        ),
    )


@router.get("/dashboard")
def dashboard(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
    q: str | None = Query(default=None, alias="q"),
    status: str | None = Query(default=None, alias="status"),
    sort: str | None = Query(default=None, alias="sort"),
):
    request.state.user = user
    settings: Settings = request.app.state.settings

    billing = db.scalar(select(BillingAccount).where(BillingAccount.user_id == user.id))
    subscription_status = billing.subscription_status if billing else "inactive"

    status_filter = (status or "all").lower()
    if status_filter not in {"all", "completed", "failed", "processing"}:
        status_filter = "all"

    sort_choice = (sort or "newest").lower()
    if sort_choice not in {"newest", "oldest", "status"}:
        sort_choice = "newest"

    stmt = (
        select(AnalysisJob, Document)
        .join(Document, Document.id == AnalysisJob.document_id)
        .where(AnalysisJob.user_id == user.id)
    )
    if q:
        stmt = stmt.where(Document.original_filename.ilike(f"%{q}%"))
    if status_filter == "completed":
        stmt = stmt.where(AnalysisJob.status == JobStatus.completed.value)
    elif status_filter == "failed":
        stmt = stmt.where(AnalysisJob.status == JobStatus.failed.value)
    elif status_filter == "processing":
        stmt = stmt.where(AnalysisJob.status.in_([JobStatus.pending.value, JobStatus.running.value]))

    if sort_choice == "oldest":
        stmt = stmt.order_by(AnalysisJob.created_at)
    elif sort_choice == "status":
        stmt = stmt.order_by(AnalysisJob.status, desc(AnalysisJob.created_at))
    else:
        stmt = stmt.order_by(desc(AnalysisJob.created_at))

    rows = db.execute(stmt.limit(25)).all()

    latest_row = db.execute(
        select(AnalysisJob, Document)
        .join(Document, Document.id == AnalysisJob.document_id)
        .where(AnalysisJob.user_id == user.id)
        .order_by(desc(AnalysisJob.created_at))
        .limit(1)
    ).first()

    latest_job = None
    if latest_row:
        job, doc = latest_row
        latest_job = {
            "id": job.id,
            "status": job.status,
            "created_at": job.created_at.isoformat(),
            "created_at_human": _human_date(job.created_at),
            "created_at_relative": _relative_time(job.created_at),
            "filename": doc.original_filename,
            "error_message": _safe_error_message(settings, job.error_message),
        }

    jobs = [
        {
            "id": job.id,
            "status": job.status,
            "created_at": job.created_at.isoformat(),
            "created_at_human": _human_date(job.created_at),
            "created_at_relative": _relative_time(job.created_at),
            "filename": doc.original_filename,
            "error_message": _safe_error_message(settings, job.error_message),
        }
        for job, doc in rows
    ]

    billing_required = settings.billing_enabled
    subscription_active = _subscription_active(billing)

    return templates.TemplateResponse(
        "dashboard.html",
        template_context(
            request,
            title="Analyze citations",
            jobs=jobs,
            billing_required=billing_required,
            subscription_active=subscription_active,
            subscription_status=subscription_status,
            query=q or "",
            status_filter=status_filter,
            sort_choice=sort_choice,
            max_upload_mb=settings.max_upload_mb,
            latest_job=latest_job,
        ),
    )


@router.post("/upload")
def upload(
    request: Request,
    file: UploadFile,
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="upload",
        limit=settings.rate_limit_upload,
        window_seconds=settings.rate_limit_window_seconds,
    )

    require_csrf(request, csrf_token)
    if settings.maintenance_mode:
        raise HTTPException(status_code=503, detail=settings.maintenance_message)

    if settings.billing_enabled:
        billing = db.scalar(select(BillingAccount).where(BillingAccount.user_id == user.id))
        if not _subscription_active(billing):
            raise HTTPException(status_code=402, detail="Active subscription required")

    stored = save_upload(settings, file)

    doc = Document(
        user_id=user.id,
        original_filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        storage_path=stored.storage_path,
        sha256=stored.sha256,
        created_at=dt.datetime.now(dt.UTC),
    )
    db.add(doc)
    db.flush()

    job = AnalysisJob(
        user_id=user.id,
        document_id=doc.id,
        status=JobStatus.pending.value,
        created_at=dt.datetime.now(dt.UTC),
    )
    db.add(job)
    db.flush()

    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


@router.get("/jobs/{job_id}")
def job_page(
    request: Request,
    job_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings

    row = db.execute(
        select(AnalysisJob, Document)
        .join(Document, Document.id == AnalysisJob.document_id)
        .where(AnalysisJob.id == job_id, AnalysisJob.user_id == user.id)
    ).first()
    if not row:
        raise HTTPException(status_code=404)
    job, doc = row

    report = _load_report(job)
    data_sources = json.loads(job.sources_json) if job.sources_json else None
    methodology_md = job.methodology_md or ""
    if not settings.expose_sensitive_report_fields:
        data_sources = _redact_sources(data_sources)
        methodology_md = _redact_methodology(methodology_md)

    return templates.TemplateResponse(
        "job.html",
        template_context(
            request,
            title="Job",
            job={
                "id": job.id,
                "status": job.status,
                "filename": doc.original_filename,
                "error_message": _safe_error_message(settings, job.error_message),
                "access_token_hint": job.access_token_hint,
                "access_token_expires_at": job.access_token_expires_at.isoformat() if job.access_token_expires_at else None,
                "access_token_expires_at_human": _human_datetime(job.access_token_expires_at)
                if job.access_token_expires_at
                else None,
                "access_token_expired": _token_expired(job),
            },
            report=report,
            data_sources=data_sources,
            methodology_md=methodology_md,
            public_view=False,
            hide_report_access=True,
        ),
    )


@router.post("/jobs/{job_id}/access-token")
def job_access_token(
    request: Request,
    job_id: str,
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="job-access-token",
        limit=settings.rate_limit_api,
        window_seconds=settings.rate_limit_window_seconds,
    )
    require_csrf(request, csrf_token)
    if settings.maintenance_mode:
        raise HTTPException(status_code=503, detail=settings.maintenance_message)

    row = db.execute(
        select(AnalysisJob, Document)
        .join(Document, Document.id == AnalysisJob.document_id)
        .where(AnalysisJob.id == job_id, AnalysisJob.user_id == user.id)
    ).first()
    if not row:
        raise HTTPException(status_code=404)
    job, doc = row

    token = generate_access_token()
    job.access_token_hash = hash_token(token)
    job.access_token_hint = access_token_hint(token)
    job.access_token_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(days=settings.access_token_days)
    db.commit()

    report = _load_report(job)
    data_sources = json.loads(job.sources_json) if job.sources_json else None
    methodology_md = job.methodology_md or ""
    if not settings.expose_sensitive_report_fields:
        data_sources = _redact_sources(data_sources)
        methodology_md = _redact_methodology(methodology_md)

    return templates.TemplateResponse(
        "job.html",
        template_context(
            request,
            title="Job",
            job={
                "id": job.id,
                "status": job.status,
                "filename": doc.original_filename,
                "error_message": _safe_error_message(settings, job.error_message),
                "access_token_hint": job.access_token_hint,
                "access_token_expires_at": job.access_token_expires_at.isoformat() if job.access_token_expires_at else None,
                "access_token_expires_at_human": _human_datetime(job.access_token_expires_at)
                if job.access_token_expires_at
                else None,
                "access_token_expired": _token_expired(job),
            },
            report=report,
            data_sources=data_sources,
            methodology_md=methodology_md,
            access_token=token,
            public_view=False,
            hide_report_access=True,
        ),
    )


@router.get("/api/jobs/{job_id}")
def job_api(
    request: Request,
    job_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="api-jobs",
        limit=settings.rate_limit_api,
        window_seconds=settings.rate_limit_window_seconds,
    )

    job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.user_id == user.id))
    if not job:
        raise HTTPException(status_code=404)

    data_sources = json.loads(job.sources_json) if job.sources_json else None
    methodology_md = job.methodology_md
    if not settings.expose_sensitive_report_fields:
        data_sources = _redact_sources(data_sources)
        methodology_md = _redact_methodology(methodology_md)

    payload = {
        "id": job.id,
        "status": job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_message": _safe_error_message(settings, job.error_message),
        "report": json.loads(job.report_json) if job.report_json else None,
        "data_sources": data_sources,
        "methodology_md": methodology_md,
    }
    return payload


def _event_payload(event: AnalysisJobEvent) -> dict:
    return {
        "id": event.id,
        "stage": event.stage,
        "message": event.message,
        "progress": event.progress,
        "created_at": event.created_at.isoformat(),
    }


def _require_access_job(db: Session, token_hash: str) -> AnalysisJob:
    job = db.scalar(select(AnalysisJob).where(AnalysisJob.access_token_hash == token_hash))
    if not job:
        raise HTTPException(status_code=404)
    now = dt.datetime.now(dt.UTC)
    if job.access_token_expires_at is None or job.access_token_expires_at < now:
        raise HTTPException(status_code=403, detail="Access token expired.")
    return job


@router.get("/api/reports/{token}")
def report_api(
    request: Request,
    token: str,
    db: Session = Depends(db_session),
):
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="api-reports",
        limit=settings.rate_limit_api,
        window_seconds=settings.rate_limit_window_seconds,
    )
    token_hash = hash_token(token.strip())
    job = _require_access_job(db, token_hash)
    return {
        "id": job.id,
        "status": job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_message": _safe_error_message(settings, job.error_message),
        "report": json.loads(job.report_json) if job.report_json else None,
    }


@router.get("/api/jobs/{job_id}/events")
def job_events(
    request: Request,
    job_id: str,
    since_id: int = Query(0, ge=0),
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="job-events",
        limit=settings.rate_limit_events,
        window_seconds=settings.rate_limit_window_seconds,
    )

    job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.user_id == user.id))
    if not job:
        raise HTTPException(status_code=404)

    rows = db.execute(
        select(AnalysisJobEvent)
        .where(AnalysisJobEvent.job_id == job_id, AnalysisJobEvent.id > since_id)
        .order_by(AnalysisJobEvent.id)
    ).scalars().all()

    return {
        "status": job.status,
        "error_message": _safe_error_message(settings, job.error_message),
        "events": [_event_payload(ev) for ev in rows],
    }


@router.get("/api/reports/{token}/events")
def report_events(
    request: Request,
    token: str,
    since_id: int = Query(0, ge=0),
    db: Session = Depends(db_session),
):
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="report-events",
        limit=settings.rate_limit_events,
        window_seconds=settings.rate_limit_window_seconds,
    )
    token_hash = hash_token(token.strip())
    job = _require_access_job(db, token_hash)

    rows = db.execute(
        select(AnalysisJobEvent)
        .where(AnalysisJobEvent.job_id == job.id, AnalysisJobEvent.id > since_id)
        .order_by(AnalysisJobEvent.id)
    ).scalars().all()

    return {
        "status": job.status,
        "error_message": _safe_error_message(settings, job.error_message),
        "events": [_event_payload(ev) for ev in rows],
    }


@router.get("/api/jobs/{job_id}/stream")
async def job_stream(
    request: Request,
    job_id: str,
    user: User = Depends(require_user),
):
    request.state.user = user
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="job-stream-open",
        limit=settings.rate_limit_stream,
        window_seconds=settings.rate_limit_window_seconds,
    )
    SessionLocal = get_sessionmaker(settings)
    slot_key = acquire_stream_slot(
        request,
        settings=settings,
        key="job-stream",
        max_active=settings.rate_limit_stream,
    )

    with SessionLocal() as db:
        job_exists = db.scalar(select(AnalysisJob.id).where(AnalysisJob.id == job_id, AnalysisJob.user_id == user.id))
        if not job_exists:
            raise HTTPException(status_code=404)

    async def event_stream():
        last_id = 0
        terminal = {JobStatus.completed.value, JobStatus.failed.value}
        try:
            while True:
                if await request.is_disconnected():
                    break

                with SessionLocal() as db:
                    rows = db.execute(
                        select(AnalysisJobEvent)
                        .where(AnalysisJobEvent.job_id == job_id, AnalysisJobEvent.id > last_id)
                        .order_by(AnalysisJobEvent.id)
                    ).scalars().all()
                    for ev in rows:
                        payload = json.dumps(_event_payload(ev), ensure_ascii=False)
                        yield f"event: progress\ndata: {payload}\n\n"
                    if rows:
                        last_id = rows[-1].id

                    job = db.get(AnalysisJob, job_id)
                    if job:
                        status_payload = json.dumps(
                            {"status": job.status, "error_message": _safe_error_message(settings, job.error_message)},
                            ensure_ascii=False,
                        )
                        yield f"event: status\ndata: {status_payload}\n\n"
                        if job.status in terminal:
                            done_payload = json.dumps({"status": job.status}, ensure_ascii=False)
                            yield f"event: done\ndata: {done_payload}\n\n"
                            break

                await asyncio.sleep(1.0)
        finally:
            release_stream_slot(slot_key)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@router.get("/api/reports/{token}/stream")
async def report_stream(
    request: Request,
    token: str,
):
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="report-stream-open",
        limit=settings.rate_limit_stream,
        window_seconds=settings.rate_limit_window_seconds,
    )
    token_hash = hash_token(token.strip())
    SessionLocal = get_sessionmaker(settings)
    slot_key = acquire_stream_slot(
        request,
        settings=settings,
        key="report-stream",
        max_active=settings.rate_limit_stream,
    )

    with SessionLocal() as db:
        _require_access_job(db, token_hash)

    async def event_stream():
        last_id = 0
        terminal = {JobStatus.completed.value, JobStatus.failed.value}
        try:
            while True:
                if await request.is_disconnected():
                    break

                with SessionLocal() as db:
                    try:
                        job = _require_access_job(db, token_hash)
                    except HTTPException:
                        break

                    rows = db.execute(
                        select(AnalysisJobEvent)
                        .where(AnalysisJobEvent.job_id == job.id, AnalysisJobEvent.id > last_id)
                        .order_by(AnalysisJobEvent.id)
                    ).scalars().all()
                    for ev in rows:
                        payload = json.dumps(_event_payload(ev), ensure_ascii=False)
                        yield f"event: progress\ndata: {payload}\n\n"
                    if rows:
                        last_id = rows[-1].id

                    status_payload = json.dumps(
                        {"status": job.status, "error_message": _safe_error_message(settings, job.error_message)},
                        ensure_ascii=False,
                    )
                    yield f"event: status\ndata: {status_payload}\n\n"
                    if job.status in terminal:
                        done_payload = json.dumps({"status": job.status}, ensure_ascii=False)
                        yield f"event: done\ndata: {done_payload}\n\n"
                        break

                await asyncio.sleep(1.0)
        finally:
            release_stream_slot(slot_key)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
