from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from server.miscite.config import Settings
from server.miscite.db import db_session
from server.miscite.models import AnalysisJob, BillingAccount, Document, JobStatus, User
from server.miscite.security import require_csrf, require_user
from server.miscite.storage import save_upload
from server.miscite.web import template_context, templates

router = APIRouter()


def _subscription_active(account: BillingAccount | None) -> bool:
    if account is None:
        return False
    return account.subscription_status in {"active", "trialing"}


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


@router.get("/dashboard")
def dashboard(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings

    billing = db.scalar(select(BillingAccount).where(BillingAccount.user_id == user.id))
    subscription_status = billing.subscription_status if billing else "inactive"

    rows = db.execute(
        select(AnalysisJob, Document)
        .join(Document, Document.id == AnalysisJob.document_id)
        .where(AnalysisJob.user_id == user.id)
        .order_by(desc(AnalysisJob.created_at))
        .limit(25)
    ).all()

    jobs = [
        {
            "id": job.id,
            "status": job.status,
            "created_at": job.created_at.isoformat(),
            "filename": doc.original_filename,
        }
        for job, doc in rows
    ]

    billing_required = settings.billing_enabled
    subscription_active = _subscription_active(billing)

    return templates.TemplateResponse(
        "dashboard.html",
        template_context(
            request,
            title="Dashboard",
            jobs=jobs,
            billing_required=billing_required,
            subscription_active=subscription_active,
            subscription_status=subscription_status,
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

    report = None
    if job.report_json:
        try:
            report = json.loads(job.report_json)
        except Exception:
            report = None

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
            },
            report=report,
            methodology_md=job.methodology_md or "",
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
