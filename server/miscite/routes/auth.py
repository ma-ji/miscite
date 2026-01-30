from __future__ import annotations

import datetime as dt
import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from server.miscite.config import Settings
from server.miscite.db import db_session
from server.miscite.email import send_login_code_email
from server.miscite.models import LoginCode, User
from server.miscite.rate_limit import enforce_rate_limit
from server.miscite.security import (
    clear_csrf_cookie,
    clear_session_cookie,
    create_session,
    delete_session,
    get_session_cookie,
    hash_login_code,
    hash_password,
    require_csrf,
    require_user,
    set_csrf_cookie,
    set_session_cookie,
)
from server.miscite.turnstile import verify_turnstile
from server.miscite.web import template_context, templates

router = APIRouter()


_SESSION_CHOICES = {
    "session": {"label": "This session", "days": None},
    "7": {"label": "7 days", "days": 7},
    "30": {"label": "30 days", "days": 30},
}


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _session_choice(raw: str | None, settings: Settings) -> tuple[str, int, bool]:
    key = (raw or "").strip().lower()
    if key not in _SESSION_CHOICES:
        key = "session"
    days = _SESSION_CHOICES[key]["days"]
    if days is None:
        return key, settings.session_days, False
    return key, int(days), True


def _generate_login_code(length: int) -> str:
    value = secrets.randbelow(10**length)
    return str(value).zfill(length)


def _mailgun_ready(settings: Settings) -> bool:
    return bool(settings.mailgun_api_key and settings.mailgun_domain and settings.mailgun_sender)


def _turnstile_ready(settings: Settings) -> bool:
    return bool(settings.turnstile_site_key and settings.turnstile_secret_key)


def _client_ip(request: Request, settings: Settings) -> str | None:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else None


@router.get("/login")
def login_page(request: Request, email: str | None = None, session_length: str | None = None):
    settings: Settings = request.app.state.settings
    session_choice, _, _ = _session_choice(session_length, settings)
    return templates.TemplateResponse(
        "login.html",
        template_context(
            request,
            title="Sign in",
            login_email=email or "",
            session_choice=session_choice,
            login_step="request",
            code_sent=False,
            login_code_length=settings.login_code_length,
            login_code_ttl_minutes=settings.login_code_ttl_minutes,
            turnstile_site_key=settings.turnstile_site_key,
        ),
    )


@router.post("/login/request")
def login_request(
    request: Request,
    email: str = Form(...),
    session_length: str = Form("session"),
    turnstile_response: str = Form("", alias="cf-turnstile-response"),
    db: Session = Depends(db_session),
):
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="login_request",
        limit=settings.rate_limit_login_request,
        window_seconds=settings.rate_limit_window_seconds,
    )
    normalized_email = _normalize_email(email)
    session_choice, _, _ = _session_choice(session_length, settings)
    if not normalized_email:
        return templates.TemplateResponse(
            "login.html",
            template_context(
                request,
                title="Sign in",
                login_email="",
                session_choice=session_choice,
                login_step="request",
                code_sent=False,
                login_code_length=settings.login_code_length,
                login_code_ttl_minutes=settings.login_code_ttl_minutes,
                turnstile_site_key=settings.turnstile_site_key,
                flash={"level": "red", "message": "Enter a valid email address."},
            ),
            status_code=400,
        )

    if not _turnstile_ready(settings):
        return templates.TemplateResponse(
            "login.html",
            template_context(
                request,
                title="Sign in",
                login_email=normalized_email,
                session_choice=session_choice,
                login_step="request",
                code_sent=False,
                login_code_length=settings.login_code_length,
                login_code_ttl_minutes=settings.login_code_ttl_minutes,
                turnstile_site_key=settings.turnstile_site_key,
                flash={"level": "red", "message": "Turnstile is not configured. Contact support."},
            ),
            status_code=503,
        )

    ok, error = verify_turnstile(
        settings,
        token=turnstile_response,
        remote_ip=_client_ip(request, settings),
    )
    if not ok:
        return templates.TemplateResponse(
            "login.html",
            template_context(
                request,
                title="Sign in",
                login_email=normalized_email,
                session_choice=session_choice,
                login_step="request",
                code_sent=False,
                login_code_length=settings.login_code_length,
                login_code_ttl_minutes=settings.login_code_ttl_minutes,
                turnstile_site_key=settings.turnstile_site_key,
                flash={"level": "red", "message": error or "Turnstile verification failed."},
            ),
            status_code=403,
        )

    if not _mailgun_ready(settings):
        return templates.TemplateResponse(
            "login.html",
            template_context(
                request,
                title="Sign in",
                login_email=normalized_email,
                session_choice=session_choice,
                login_step="request",
                code_sent=False,
                login_code_length=settings.login_code_length,
                login_code_ttl_minutes=settings.login_code_ttl_minutes,
                turnstile_site_key=settings.turnstile_site_key,
                flash={"level": "red", "message": "Email delivery is not configured. Contact support."},
            ),
            status_code=503,
        )

    now = dt.datetime.now(dt.UTC)
    db.execute(delete(LoginCode).where(LoginCode.expires_at < now))
    db.execute(delete(LoginCode).where(LoginCode.email == normalized_email))

    code = _generate_login_code(settings.login_code_length)
    db.add(
        LoginCode(
            email=normalized_email,
            code_hash=hash_login_code(code),
            created_at=now,
            expires_at=now + dt.timedelta(minutes=settings.login_code_ttl_minutes),
        )
    )
    try:
        send_login_code_email(settings, to_email=normalized_email, code=code)
    except Exception:
        db.rollback()
        return templates.TemplateResponse(
            "login.html",
            template_context(
                request,
                title="Sign in",
                login_email=normalized_email,
                session_choice=session_choice,
                login_step="request",
                code_sent=False,
                login_code_length=settings.login_code_length,
                login_code_ttl_minutes=settings.login_code_ttl_minutes,
                turnstile_site_key=settings.turnstile_site_key,
                flash={"level": "red", "message": "We could not send your code. Please try again."},
            ),
            status_code=502,
        )
    db.commit()

    return templates.TemplateResponse(
        "login.html",
        template_context(
            request,
            title="Sign in",
            login_email=normalized_email,
            session_choice=session_choice,
            login_step="verify",
            code_sent=True,
            login_code_length=settings.login_code_length,
            login_code_ttl_minutes=settings.login_code_ttl_minutes,
            turnstile_site_key=settings.turnstile_site_key,
            flash={"level": "green", "message": "Check your inbox for your sign-in code."},
        ),
    )


@router.post("/login/verify")
def login_verify(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    session_length: str = Form("session"),
    db: Session = Depends(db_session),
):
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="login_verify",
        limit=settings.rate_limit_login_verify,
        window_seconds=settings.rate_limit_window_seconds,
    )
    normalized_email = _normalize_email(email)
    code_value = "".join(code.split())
    session_choice, session_days, persistent = _session_choice(session_length, settings)
    if not normalized_email:
        return templates.TemplateResponse(
            "login.html",
            template_context(
                request,
                title="Sign in",
                login_email=normalized_email,
                session_choice=session_choice,
                login_step="request",
                code_sent=False,
                login_code_length=settings.login_code_length,
                login_code_ttl_minutes=settings.login_code_ttl_minutes,
                turnstile_site_key=settings.turnstile_site_key,
                flash={"level": "red", "message": "Enter your email first."},
            ),
            status_code=400,
        )
    if not code_value:
        return templates.TemplateResponse(
            "login.html",
            template_context(
                request,
                title="Sign in",
                login_email=normalized_email,
                session_choice=session_choice,
                login_step="verify",
                code_sent=False,
                login_code_length=settings.login_code_length,
                login_code_ttl_minutes=settings.login_code_ttl_minutes,
                turnstile_site_key=settings.turnstile_site_key,
                flash={"level": "red", "message": "Enter your sign-in code."},
            ),
            status_code=400,
        )

    now = dt.datetime.now(dt.UTC)
    db.execute(delete(LoginCode).where(LoginCode.expires_at < now))
    login_code = db.scalar(
        select(LoginCode)
        .where(LoginCode.email == normalized_email)
        .where(LoginCode.expires_at > now)
        .order_by(LoginCode.created_at.desc())
    )
    if not login_code or hash_login_code(code_value) != login_code.code_hash:
        return templates.TemplateResponse(
            "login.html",
            template_context(
                request,
                title="Sign in",
                login_email=normalized_email,
                session_choice=session_choice,
                login_step="verify",
                code_sent=False,
                login_code_length=settings.login_code_length,
                login_code_ttl_minutes=settings.login_code_ttl_minutes,
                turnstile_site_key=settings.turnstile_site_key,
                flash={"level": "red", "message": "Invalid or expired code."},
            ),
            status_code=401,
        )

    if settings.maintenance_mode:
        existing = db.scalar(select(User).where(User.email == normalized_email))
        if existing is None:
            return templates.TemplateResponse(
                "login.html",
                template_context(
                    request,
                    title="Sign in",
                    login_email=normalized_email,
                    session_choice=session_choice,
                    login_step="verify",
                    code_sent=False,
                    login_code_length=settings.login_code_length,
                    login_code_ttl_minutes=settings.login_code_ttl_minutes,
                    turnstile_site_key=settings.turnstile_site_key,
                    flash={"level": "amber", "message": settings.maintenance_message},
                ),
                status_code=503,
            )

    db.execute(delete(LoginCode).where(LoginCode.email == normalized_email))
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        user = User(email=normalized_email, password_hash=hash_password(secrets.token_urlsafe(16)))
        db.add(user)
        db.flush()

    token, csrf = create_session(db, user=user, session_days=session_days)
    response = RedirectResponse("/dashboard", status_code=303)
    max_age_seconds = int(dt.timedelta(days=session_days).total_seconds()) if persistent else None
    set_session_cookie(response, token=token, settings=settings, max_age_seconds=max_age_seconds)
    set_csrf_cookie(response, token=csrf, settings=settings, max_age_seconds=max_age_seconds)
    return response


@router.get("/register")
def register_page(request: Request):
    return RedirectResponse("/login", status_code=303)


@router.post("/register")
def register_action(request: Request):
    return RedirectResponse("/login", status_code=303)


@router.post("/logout")
def logout_action(
    request: Request,
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    _ = user
    require_csrf(request, csrf_token)
    token = get_session_cookie(request)
    if token:
        delete_session(db, token=token)
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookie(response)
    clear_csrf_cookie(response)
    return response
