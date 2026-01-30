from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from server.miscite.config import Settings
from server.miscite.db import get_sessionmaker

router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.get("/readyz")
def readyz(request: Request):
    settings: Settings = request.app.state.settings

    if not settings.openrouter_api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY missing")
    if not settings.retractionwatch_csv.exists():
        raise HTTPException(status_code=503, detail="Retraction Watch dataset missing")
    if not (settings.predatory_api_enabled or settings.predatory_csv.exists()):
        raise HTTPException(status_code=503, detail="Predatory venue source missing")

    SessionLocal = get_sessionmaker(settings)
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    return {"ok": True}
