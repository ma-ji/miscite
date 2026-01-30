from __future__ import annotations

import asyncio
import datetime as dt
import json

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from server.miscite.config import Settings
from server.miscite.db import db_session, get_sessionmaker
from server.miscite.models import AnalysisJob, AnalysisJobEvent, BillingAccount, Document, JobStatus, User
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


def _load_report(job: AnalysisJob) -> dict | None:
    if not job.report_json:
        return None
    try:
        return json.loads(job.report_json)
    except Exception:
        return None


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
        template_context(request, title="miscite"),
    )


@router.get("/reports/access")
def report_access_form(request: Request):
    return templates.TemplateResponse(
        "report_access.html",
        template_context(request, title="Get report"),
    )


@router.post("/reports/access")
def report_access(request: Request, token: str = Form(""), db: Session = Depends(db_session)):
    token_value = token.strip()
    if not token_value:
        return templates.TemplateResponse(
            "report_access.html",
            template_context(
                request,
                title="Get report",
                access_error="Please enter an access token.",
            ),
        )

    token_hash = hash_token(token_value)
    row = db.execute(
        select(AnalysisJob, Document)
        .join(Document, Document.id == AnalysisJob.document_id)
        .where(AnalysisJob.access_token_hash == token_hash)
        .limit(1)
    ).first()
    if not row:
        return templates.TemplateResponse(
            "report_access.html",
            template_context(
                request,
                title="Get report",
                access_error="That token was not recognized. Double-check and try again.",
            ),
        )

    job, doc = row
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
                "error_message": job.error_message,
                "access_token_hint": job.access_token_hint,
            },
            report=report,
            methodology_md="",
            public_view=True,
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
            "error_message": job.error_message,
        }

    jobs = [
        {
            "id": job.id,
            "status": job.status,
            "created_at": job.created_at.isoformat(),
            "created_at_human": _human_date(job.created_at),
            "created_at_relative": _relative_time(job.created_at),
            "filename": doc.original_filename,
            "error_message": job.error_message,
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

    require_csrf(request, csrf_token)

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

    row = db.execute(
        select(AnalysisJob, Document)
        .join(Document, Document.id == AnalysisJob.document_id)
        .where(AnalysisJob.id == job_id, AnalysisJob.user_id == user.id)
    ).first()
    if not row:
        raise HTTPException(status_code=404)
    job, doc = row

    report = _load_report(job)

    return templates.TemplateResponse(
        "job.html",
        template_context(
            request,
            title="Job",
            job={
                "id": job.id,
                "status": job.status,
                "filename": doc.original_filename,
                "error_message": job.error_message,
                "access_token_hint": job.access_token_hint,
            },
            report=report,
            methodology_md=job.methodology_md or "",
            public_view=False,
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
    require_csrf(request, csrf_token)

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
    db.commit()

    report = _load_report(job)

    return templates.TemplateResponse(
        "job.html",
        template_context(
            request,
            title="Job",
            job={
                "id": job.id,
                "status": job.status,
                "filename": doc.original_filename,
                "error_message": job.error_message,
                "access_token_hint": job.access_token_hint,
            },
            report=report,
            methodology_md=job.methodology_md or "",
            access_token=token,
            public_view=False,
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

    job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.user_id == user.id))
    if not job:
        raise HTTPException(status_code=404)

    payload = {
        "id": job.id,
        "status": job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_message": job.error_message,
        "report": json.loads(job.report_json) if job.report_json else None,
        "data_sources": json.loads(job.sources_json) if job.sources_json else None,
        "methodology_md": job.methodology_md,
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


@router.get("/api/jobs/{job_id}/events")
def job_events(
    request: Request,
    job_id: str,
    since_id: int = Query(0, ge=0),
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user

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
        "error_message": job.error_message,
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
    SessionLocal = get_sessionmaker(settings)

    with SessionLocal() as db:
        job_exists = db.scalar(select(AnalysisJob.id).where(AnalysisJob.id == job_id, AnalysisJob.user_id == user.id))
        if not job_exists:
            raise HTTPException(status_code=404)

    async def event_stream():
        last_id = 0
        terminal = {JobStatus.completed.value, JobStatus.failed.value}
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
                        {"status": job.status, "error_message": job.error_message},
                        ensure_ascii=False,
                    )
                    yield f"event: status\ndata: {status_payload}\n\n"
                    if job.status in terminal:
                        done_payload = json.dumps({"status": job.status}, ensure_ascii=False)
                        yield f"event: done\ndata: {done_payload}\n\n"
                        break

            await asyncio.sleep(1.0)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
