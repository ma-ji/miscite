from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import os
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.miscite.config import Settings
from server.miscite.db import db_session
from server.miscite.models import User, UserSession


_COOKIE_NAME = "miscite_session"
_CSRF_COOKIE_NAME = "miscite_csrf"


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_token(value: str) -> str:
    return _sha256_hex(value)


def generate_access_token() -> str:
    return secrets.token_urlsafe(24)


def access_token_hint(token: str) -> str:
    return token[-6:] if len(token) >= 6 else token


def _as_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    salt = os.urandom(16)
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256$%d$%s$%s" % (
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations_str, salt_b64, digest_b64 = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def create_session(db: Session, *, user: User, session_days: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(16)
    now = dt.datetime.now(dt.UTC)
    expires_at = now + dt.timedelta(days=session_days)

    db.add(
        UserSession(
            user_id=user.id,
            token_hash=_sha256_hex(token),
            csrf_hash=_sha256_hex(csrf),
            created_at=now,
            expires_at=expires_at,
        )
    )
    db.commit()
    return token, csrf


def delete_session(db: Session, *, token: str) -> None:
    token_hash = _sha256_hex(token)
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
    if session is None:
        return
    db.delete(session)
    db.commit()


def get_session_cookie(request: Request) -> str | None:
    token = request.cookies.get(_COOKIE_NAME)
    return token if token else None


def get_csrf_cookie(request: Request) -> str | None:
    token = request.cookies.get(_CSRF_COOKIE_NAME)
    return token if token else None


def set_session_cookie(response, *, token: str, settings: Settings) -> None:
    response.set_cookie(
        _COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=int(dt.timedelta(days=settings.session_days).total_seconds()),
        path="/",
    )


def set_csrf_cookie(response, *, token: str, settings: Settings) -> None:
    response.set_cookie(
        _CSRF_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=int(dt.timedelta(days=settings.session_days).total_seconds()),
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(_COOKIE_NAME, path="/")


def clear_csrf_cookie(response) -> None:
    response.delete_cookie(_CSRF_COOKIE_NAME, path="/")


def require_user(request: Request, db: Session = Depends(db_session)) -> User:
    token = get_session_cookie(request)
    if not token:
        raise HTTPException(status_code=401)

    token_hash = _sha256_hex(token)
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
    if session is None:
        raise HTTPException(status_code=401)
    if _as_utc(session.expires_at) < dt.datetime.now(dt.UTC):
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401)

    user = db.scalar(select(User).where(User.id == session.user_id))
    if user is None:
        raise HTTPException(status_code=401)
    request.state._csrf_hash = session.csrf_hash
    return user


def get_user_optional(request: Request, db: Session = Depends(db_session)) -> User | None:
    token = get_session_cookie(request)
    if not token:
        return None
    token_hash = _sha256_hex(token)
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
    if session is None or _as_utc(session.expires_at) < dt.datetime.now(dt.UTC):
        return None
    user = db.scalar(select(User).where(User.id == session.user_id))
    if user is None:
        return None
    request.state._csrf_hash = session.csrf_hash
    return user


def require_csrf(request: Request, csrf_token: str) -> None:
    csrf_hash = getattr(request.state, "_csrf_hash", None)
    if not csrf_hash:
        raise HTTPException(status_code=403, detail="Missing CSRF context")
    if _sha256_hex(csrf_token) != csrf_hash:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def require_user_from_request(request: Request, db: Session) -> User:
    return require_user(request, db)
