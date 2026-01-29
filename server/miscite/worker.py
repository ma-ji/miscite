from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.orm import Session

from server.miscite.analysis.pipeline import analyze_document
from server.miscite.config import Settings
from server.miscite.db import get_sessionmaker, init_db
from server.miscite.models import AnalysisJob, Document, JobStatus
from server.miscite.sources.predatory_sync import sync_predatory_datasets
from server.miscite.sources.retractionwatch_sync import sync_retractionwatch_dataset


def _claim_next_job(db: Session) -> str | None:
    job_id = db.scalar(
        select(AnalysisJob.id)
        .where(AnalysisJob.status == JobStatus.pending.value)
        .order_by(AnalysisJob.created_at)
        .limit(1)
    )
    if not job_id:
        return None

    now = dt.datetime.now(dt.UTC)
    result = db.execute(
        update(AnalysisJob)
        .where(AnalysisJob.id == job_id, AnalysisJob.status == JobStatus.pending.value)
        .values(status=JobStatus.running.value, started_at=now, error_message=None)
    )
    if result.rowcount == 1:
        return job_id
    return None


def _load_job(db: Session, job_id: str) -> tuple[AnalysisJob, Document] | None:
    job = db.get(AnalysisJob, job_id)
    if not job:
        return None
    doc = db.get(Document, job.document_id)
    if not doc:
        return None
    return job, doc


def _process_job(settings: Settings, job_id: str) -> None:
    SessionLocal = get_sessionmaker(settings)
    db = SessionLocal()
    try:
        row = _load_job(db, job_id)
        if not row:
            return
        job, doc = row

        report, sources, methodology_md = analyze_document(Path(doc.storage_path), settings=settings)

        job.report_json = json.dumps(report, ensure_ascii=False)
        job.sources_json = json.dumps(sources, ensure_ascii=False)
        job.methodology_md = methodology_md
        job.status = JobStatus.completed.value
        job.finished_at = dt.datetime.now(dt.UTC)
        db.commit()
    except Exception as e:
        try:
            row = _load_job(db, job_id)
            if row:
                job, _doc = row
                job.status = JobStatus.failed.value
                job.error_message = str(e)
                job.finished_at = dt.datetime.now(dt.UTC)
                db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()


def run_worker_loop(settings: Settings, *, process_index: int = 0) -> None:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    log = logging.getLogger(f"miscite.worker.{process_index}")

    init_db(settings)

    # Ensure storage dir exists for any relative paths.
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    next_rw_sync_at = 0.0
    if settings.rw_sync_enabled:
        result = sync_retractionwatch_dataset(settings, force=False)
        if result.updated:
            log.info("Retraction Watch dataset synced (%s): %s", result.method, result.target_csv)
        next_rw_sync_at = time.time() + 3600.0

    next_pred_sync_at = 0.0
    if settings.predatory_sync_enabled:
        result = sync_predatory_datasets(settings, force=False)
        if result.updated:
            log.info("Predatory lists synced: %s", result.target_csv)
        next_pred_sync_at = time.time() + 3600.0

    SessionLocal = get_sessionmaker(settings)
    log.info("Worker started (process_index=%s, db=%s)", process_index, settings.db_url)

    while True:
        if settings.rw_sync_enabled and time.time() >= next_rw_sync_at:
            result = sync_retractionwatch_dataset(settings, force=False)
            if result.updated:
                log.info("Retraction Watch dataset synced (%s): %s", result.method, result.target_csv)
            next_rw_sync_at = time.time() + 3600.0

        if settings.predatory_sync_enabled and time.time() >= next_pred_sync_at:
            result = sync_predatory_datasets(settings, force=False)
            if result.updated:
                log.info("Predatory lists synced: %s", result.target_csv)
            next_pred_sync_at = time.time() + 3600.0

        db = SessionLocal()
        try:
            job_id = _claim_next_job(db)
            db.commit()
        except Exception:
            db.rollback()
            job_id = None
        finally:
            db.close()

        if not job_id:
            time.sleep(settings.worker_poll_seconds)
            continue

        log.info("Processing job %s", job_id)
        try:
            _process_job(settings, job_id)
            log.info("Completed job %s", job_id)
        except Exception as e:
            log.exception("Job %s failed: %s", job_id, e)
