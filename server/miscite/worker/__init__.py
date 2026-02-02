from __future__ import annotations

import datetime as dt
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from server.miscite.billing.costing import compute_cost
from server.miscite.billing.ledger import apply_usage_charge
from server.miscite.billing.pricing import get_openrouter_pricing
from server.miscite.billing.stripe import create_auto_charge_payment_intent
from server.miscite.billing.usage import UsageTracker
from server.miscite.analysis.pipeline import analyze_document
from server.miscite.core.cache import Cache
from server.miscite.core.config import Settings
from server.miscite.core.db import get_sessionmaker, init_db
from server.miscite.core.email import send_access_token_email
from server.miscite.core.models import AnalysisJob, AnalysisJobEvent, BillingAccount, Document, JobStatus, User
from server.miscite.core.security import access_token_hint, generate_access_token, hash_token
from server.miscite.sources.predatory_sync import sync_predatory_datasets
from server.miscite.sources.retractionwatch_sync import sync_retractionwatch_dataset


@dataclass(frozen=True)
class _AccessTokenEmail:
    token: str
    to_email: str
    job_id: str
    filename: str
    expires_at: dt.datetime | None


class JobCanceled(RuntimeError):
    """Raised when a job is manually canceled by the user."""


def _as_utc(ts: dt.datetime | None) -> dt.datetime | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=dt.UTC)
    return ts.astimezone(dt.UTC)


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
        .values(
            status=JobStatus.running.value,
            started_at=now,
            last_heartbeat_at=now,
            attempts=AnalysisJob.attempts + 1,
            error_message=None,
        )
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


def _is_job_canceled(db: Session, job_id: str) -> bool:
    status = db.scalar(select(AnalysisJob.status).where(AnalysisJob.id == job_id))
    return status == JobStatus.canceled.value


def _ensure_access_token(
    settings: Settings,
    job_id: str,
    *,
    send_existing: bool = False,
    require_completed: bool = False,
) -> _AccessTokenEmail | None:
    SessionLocal = get_sessionmaker(settings)
    db = SessionLocal()
    try:
        row = db.execute(
            select(AnalysisJob, Document, User)
            .join(Document, Document.id == AnalysisJob.document_id)
            .join(User, User.id == AnalysisJob.user_id)
            .where(AnalysisJob.id == job_id)
        ).first()
        if not row:
            return None
        job, doc, user = row
        if require_completed and job.status != JobStatus.completed.value:
            return None
        now = dt.datetime.now(dt.UTC)
        expires_at = _as_utc(job.access_token_expires_at)
        if job.access_token_hash and (expires_at is None or expires_at >= now):
            if send_existing and job.access_token_value:
                return _AccessTokenEmail(
                    token=job.access_token_value,
                    to_email=user.email,
                    job_id=job.id,
                    filename=doc.original_filename,
                    expires_at=expires_at,
                )
            return None
        token = generate_access_token()
        job.access_token_hash = hash_token(token)
        job.access_token_hint = access_token_hint(token)
        job.access_token_value = token
        job.access_token_expires_at = now + dt.timedelta(days=settings.access_token_days)
        db.add(job)
        db.commit()
        return _AccessTokenEmail(
            token=token,
            to_email=user.email,
            job_id=job.id,
            filename=doc.original_filename,
            expires_at=job.access_token_expires_at,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _process_job(settings: Settings, job_id: str) -> None:
    SessionLocal = get_sessionmaker(settings)
    db = SessionLocal()
    progress_db = SessionLocal()
    try:
        row = _load_job(db, job_id)
        if not row:
            return
        job, doc = row
        if job.status == JobStatus.canceled.value:
            return
        _record_progress(settings, job_id, "started", "Job started", 0.02, db=progress_db)

        def progress_cb(stage: str, message: str | None, progress: float | None) -> None:
            if _is_job_canceled(progress_db, job_id):
                raise JobCanceled("Canceled by user.")
            _record_progress(settings, job_id, stage, message, progress, db=progress_db)

        usage_tracker = UsageTracker()
        report, sources, methodology_md = analyze_document(
            Path(doc.storage_path),
            settings=settings,
            document_sha256=doc.sha256,
            usage_tracker=usage_tracker,
            progress_cb=progress_cb,
        )
        usage_summary = usage_tracker.summary()

        if _is_job_canceled(db, job_id):
            raise JobCanceled("Canceled by user.")

        job.report_json = json.dumps(report, ensure_ascii=False)
        job.sources_json = json.dumps(sources, ensure_ascii=False)
        job.methodology_md = methodology_md
        job.llm_usage_json = json.dumps(usage_summary, ensure_ascii=False)

        pricing_snapshot = get_openrouter_pricing(settings, cache=Cache(settings=settings), allow_stale=True)
        cost_result = None
        if pricing_snapshot is not None:
            cost_result = compute_cost(
                usage_summary=usage_summary,
                pricing=pricing_snapshot,
                multiplier=settings.billing_cost_multiplier,
                currency=settings.billing_currency,
            )
            job.llm_cost_json = json.dumps(asdict(cost_result), ensure_ascii=False)
            job.llm_cost_currency = cost_result.currency
            job.llm_cost_raw_cents = cost_result.raw_cost_cents
            job.llm_cost_cents = cost_result.final_cost_cents
            job.llm_cost_multiplier = cost_result.multiplier

        billing_status = None
        billing_error = None
        if settings.billing_enabled:
            if cost_result is None:
                billing_status = "pricing_unavailable"
                billing_error = "OpenRouter pricing unavailable."
            elif cost_result.missing_models:
                billing_status = "pricing_missing"
                billing_error = "Missing pricing for: " + ", ".join(sorted(cost_result.missing_models))
            else:
                billing_result = apply_usage_charge(
                    db,
                    settings=settings,
                    user_id=job.user_id,
                    job_id=job.id,
                    amount_cents=cost_result.final_cost_cents,
                    currency=cost_result.currency,
                )
                billing_status = billing_result.status
                billing_error = billing_result.error
                if billing_result.status == "charged":
                    job.billing_debited_at = dt.datetime.now(dt.UTC)
        else:
            billing_status = "disabled"

        job.billing_status = billing_status
        job.billing_error = billing_error
        job.status = JobStatus.completed.value
        job.finished_at = dt.datetime.now(dt.UTC)
        db.commit()
        _record_progress(settings, job_id, "completed", "Report ready", 1.0, db=progress_db)

        if settings.billing_enabled and job.billing_status == "charged":
            _maybe_auto_charge(settings, user_id=job.user_id)
    except JobCanceled as e:
        try:
            row = _load_job(db, job_id)
            if row:
                job, _doc = row
                job.status = JobStatus.canceled.value
                job.error_message = str(e) or "Canceled by user."
                job.finished_at = dt.datetime.now(dt.UTC)
                db.commit()
                _record_progress(settings, job_id, "canceled", "Canceled by user.", 1.0, db=progress_db)
        except Exception:
            db.rollback()
        return
    except Exception as e:
        try:
            row = _load_job(db, job_id)
            if row:
                job, _doc = row
                job.status = JobStatus.failed.value
                job.error_message = str(e)
                job.finished_at = dt.datetime.now(dt.UTC)
                db.commit()
                _record_progress(settings, job_id, "failed", str(e), 1.0, db=progress_db)
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()
        progress_db.close()


def _record_progress(
    settings: Settings,
    job_id: str,
    stage: str,
    message: str | None = None,
    progress: float | None = None,
    *,
    db: Session | None = None,
) -> None:
    SessionLocal = get_sessionmaker(settings)
    owns_session = False
    if db is None:
        db = SessionLocal()
        owns_session = True
    try:
        now = dt.datetime.now(dt.UTC)
        db.add(
            AnalysisJobEvent(
                job_id=job_id,
                stage=stage,
                message=message,
                progress=progress,
            )
        )
        db.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(last_heartbeat_at=now)
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        if owns_session:
            db.close()


def _maybe_auto_charge(settings: Settings, *, user_id: str) -> None:
    if not settings.billing_enabled or not settings.stripe_secret_key:
        return
    SessionLocal = get_sessionmaker(settings)
    db = SessionLocal()
    try:
        account = db.scalar(select(BillingAccount).where(BillingAccount.user_id == user_id))
        if account is None:
            return
        if not account.auto_charge_enabled:
            return
        if not account.stripe_customer_id:
            account.auto_charge_last_error = "No Stripe customer on file for auto-charge."
            db.commit()
            return

        threshold = account.auto_charge_threshold_cents or settings.billing_auto_charge_default_threshold_cents
        amount = account.auto_charge_amount_cents or settings.billing_auto_charge_default_amount_cents
        if amount < settings.billing_min_charge_cents:
            amount = settings.billing_min_charge_cents
        if amount <= 0:
            return
        if account.balance_cents >= threshold:
            return

        try:
            create_auto_charge_payment_intent(settings=settings, account=account, amount_cents=amount)
            account.auto_charge_last_error = None
        except Exception as e:
            account.auto_charge_last_error = str(e)
        db.add(account)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _reap_stale_jobs(settings: Settings) -> None:
    SessionLocal = get_sessionmaker(settings)
    db = SessionLocal()
    try:
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=settings.job_stale_seconds)
        stale = (
            db.execute(
                select(AnalysisJob)
                .where(
                    AnalysisJob.status == JobStatus.running.value,
                    or_(AnalysisJob.last_heartbeat_at.is_(None), AnalysisJob.last_heartbeat_at < cutoff),
                )
                .order_by(AnalysisJob.started_at)
            )
            .scalars()
            .all()
        )
        for job in stale:
            if settings.job_stale_action == "requeue" and job.attempts < settings.job_max_attempts:
                job.status = JobStatus.pending.value
                job.error_message = "Job re-queued after stale worker heartbeat."
                job.started_at = None
                job.finished_at = None
                job.last_heartbeat_at = None
            else:
                job.status = JobStatus.failed.value
                job.error_message = "Job failed due to stale worker heartbeat."
                job.finished_at = dt.datetime.now(dt.UTC)
            db.add(job)
        if stale:
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _reap_expired_jobs(settings: Settings) -> None:
    SessionLocal = get_sessionmaker(settings)
    db = SessionLocal()
    expired_paths: list[str] = []
    committed = False
    try:
        now = dt.datetime.now(dt.UTC)
        rows = db.execute(
            select(AnalysisJob, Document)
            .join(Document, Document.id == AnalysisJob.document_id)
            .where(
                AnalysisJob.access_token_expires_at.is_not(None),
                AnalysisJob.access_token_expires_at < now,
                AnalysisJob.status.in_(
                    [
                        JobStatus.completed.value,
                        JobStatus.failed.value,
                        JobStatus.canceled.value,
                    ]
                ),
            )
        ).all()
        if not rows:
            return
        for job, doc in rows:
            expired_paths.append(doc.storage_path)
            db.execute(delete(AnalysisJobEvent).where(AnalysisJobEvent.job_id == job.id))
            db.delete(job)
            db.delete(doc)
        db.commit()
        committed = True
    except Exception:
        db.rollback()
    finally:
        db.close()

    if not committed:
        return
    for path in expired_paths:
        try:
            Path(path).unlink()
        except OSError:
            pass


def _reap_cache(settings: Settings) -> None:
    if not settings.cache_enabled:
        return
    Cache(settings=settings).reap_expired()

    def _reap_text_cache(root: Path, ttl_days: int) -> None:
        ttl_seconds = float(ttl_days) * 86400.0
        if ttl_seconds <= 0:
            return
        if not root.exists():
            return
        now = time.time()
        try:
            paths = list(root.rglob("*.txt"))
        except OSError:
            return
        for p in paths:
            try:
                if (now - p.stat().st_mtime) > ttl_seconds:
                    p.unlink(missing_ok=True)
            except OSError:
                continue

    _reap_text_cache(settings.cache_dir / "text_extract", settings.cache_text_ttl_days)
    _reap_text_cache(settings.cache_dir / "openrouter.chat_json", settings.cache_llm_ttl_days)


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

    next_pricing_sync_at = 0.0
    if settings.billing_enabled:
        snapshot = get_openrouter_pricing(settings, cache=Cache(settings=settings), force_refresh=True)
        if snapshot is not None:
            log.info("OpenRouter pricing synced (%s models, source=%s)", len(snapshot.models), snapshot.source)
        next_pricing_sync_at = time.time() + float(settings.openrouter_pricing_refresh_minutes) * 60.0

    next_reap_at = time.time() + float(settings.job_reap_interval_seconds)

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

        if settings.billing_enabled and time.time() >= next_pricing_sync_at:
            snapshot = get_openrouter_pricing(settings, cache=Cache(settings=settings), force_refresh=True)
            if snapshot is not None:
                log.info("OpenRouter pricing synced (%s models, source=%s)", len(snapshot.models), snapshot.source)
            next_pricing_sync_at = time.time() + float(settings.openrouter_pricing_refresh_minutes) * 60.0

        if time.time() >= next_reap_at:
            _reap_stale_jobs(settings)
            _reap_expired_jobs(settings)
            _reap_cache(settings)
            next_reap_at = time.time() + float(settings.job_reap_interval_seconds)

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
            status = None
            try:
                with SessionLocal() as status_db:
                    status = status_db.scalar(select(AnalysisJob.status).where(AnalysisJob.id == job_id))
            except Exception:
                status = None

            if status == JobStatus.canceled.value:
                log.info("Canceled job %s", job_id)
                continue
            if status != JobStatus.completed.value:
                log.info("Finished job %s (status=%s)", job_id, status or "unknown")
                continue

            log.info("Completed job %s", job_id)
            try:
                payload = _ensure_access_token(settings, job_id, send_existing=True, require_completed=True)
            except Exception as e:
                payload = None
                log.warning("Failed to issue access token for job %s: %s", job_id, e)
            if payload:
                try:
                    send_access_token_email(
                        settings,
                        to_email=payload.to_email,
                        token=payload.token,
                        job_id=payload.job_id,
                        filename=payload.filename,
                        expires_at=payload.expires_at,
                    )
                    log.info("Sent access token email for job %s", job_id)
                except Exception as e:
                    log.warning("Failed to send access token email for job %s: %s", job_id, e)
        except Exception as e:
            log.exception("Job %s failed: %s", job_id, e)
