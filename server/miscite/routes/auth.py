from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.miscite.config import Settings
from server.miscite.db import db_session
from server.miscite.models import User
from server.miscite.rate_limit import enforce_rate_limit
from server.miscite.security import (
    clear_csrf_cookie,
    clear_session_cookie,
    create_session,
    delete_session,
    get_session_cookie,
    hash_password,
    require_csrf,
    require_user,
    set_csrf_cookie,
    set_session_cookie,
    verify_password,
)
from server.miscite.web import template_context, templates

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", template_context(request, title="Login"))


@router.post("/login")
def login_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(db_session),
):
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="login",
        limit=settings.rate_limit_login,
        window_seconds=settings.rate_limit_window_seconds,
    )
    normalized_email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            template_context(
                request,
                title="Login",
                flash={"level": "red", "message": "Invalid email or password."},
            ),
            status_code=401,
        )

    token, csrf = create_session(db, user=user, session_days=settings.session_days)
    response = RedirectResponse("/dashboard", status_code=303)
    set_session_cookie(response, token=token, settings=settings)
    set_csrf_cookie(response, token=csrf, settings=settings)
    return response


@router.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", template_context(request, title="Register"))


@router.post("/register")
def register_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(db_session),
):
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="register",
        limit=settings.rate_limit_register,
        window_seconds=settings.rate_limit_window_seconds,
    )
    if settings.maintenance_mode:
        return templates.TemplateResponse(
            "register.html",
            template_context(
                request,
                title="Register",
                flash={"level": "amber", "message": settings.maintenance_message},
            ),
            status_code=503,
        )
    normalized_email = email.strip().lower()

    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        return templates.TemplateResponse(
            "register.html",
            template_context(
                request,
                title="Register",
                flash={"level": "amber", "message": "Email already registered. Please login."},
            ),
            status_code=400,
        )

    user = User(email=normalized_email, password_hash=hash_password(password))
    db.add(user)
    db.flush()

    token, csrf = create_session(db, user=user, session_days=settings.session_days)
    response = RedirectResponse("/dashboard", status_code=303)
    set_session_cookie(response, token=token, settings=settings)
    set_csrf_cookie(response, token=csrf, settings=settings)
    return response


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
