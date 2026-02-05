from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from server.miscite.core.models import AnalysisJob, AnalysisJobEvent, BillingTransaction, Document


def delete_job_and_document(db: Session, *, job_id: str, document_id: str) -> bool:
    """Delete a job and related rows; return True if the document row was deleted."""
    db.execute(
        update(BillingTransaction)
        .where(BillingTransaction.job_id == job_id)
        .values(job_id=None)
    )
    db.execute(delete(AnalysisJobEvent).where(AnalysisJobEvent.job_id == job_id))
    db.execute(delete(AnalysisJob).where(AnalysisJob.id == job_id))

    remaining = db.scalar(
        select(AnalysisJob.id).where(AnalysisJob.document_id == document_id).limit(1)
    )
    if remaining is None:
        db.execute(delete(Document).where(Document.id == document_id))
        return True
    return False
