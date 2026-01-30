from __future__ import annotations

import datetime as dt

import stripe
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.miscite.config import Settings
from server.miscite.db import db_session
from server.miscite.models import BillingAccount, User
from server.miscite.rate_limit import enforce_rate_limit
from server.miscite.security import require_csrf, require_user
from server.miscite.web import template_context, templates

router = APIRouter()


def _subscription_active(account: BillingAccount | None) -> bool:
    if account is None:
        return False
    return account.subscription_status in {"active", "trialing"}


def _ensure_customer(db: Session, *, user: User, settings: Settings) -> BillingAccount:
    account = db.scalar(select(BillingAccount).where(BillingAccount.user_id == user.id))
    if account is None:
        account = BillingAccount(user_id=user.id, subscription_status="inactive", updated_at=dt.datetime.now(dt.UTC))
        db.add(account)
        db.flush()

    if account.stripe_customer_id:
        return account

    stripe.api_key = settings.stripe_secret_key
    customer = stripe.Customer.create(email=user.email, metadata={"user_id": user.id})
    account.stripe_customer_id = customer["id"]
    account.updated_at = dt.datetime.now(dt.UTC)
    return account


@router.get("/billing")
def billing_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings

    account = db.scalar(select(BillingAccount).where(BillingAccount.user_id == user.id))
    subscription_status = account.subscription_status if account else "inactive"

    return templates.TemplateResponse(
        "billing.html",
        template_context(
            request,
            title="Billing",
            billing_enabled=settings.billing_enabled,
            subscription_status=subscription_status,
            subscription_active=_subscription_active(account),
            can_open_portal=bool(account and account.stripe_customer_id),
        ),
    )


@router.post("/billing/checkout")
def billing_checkout(
    request: Request,
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="billing-checkout",
        limit=settings.rate_limit_api,
        window_seconds=settings.rate_limit_window_seconds,
    )
    require_csrf(request, csrf_token)

    if not settings.billing_enabled:
        raise HTTPException(status_code=400, detail="Billing disabled")
    if settings.maintenance_mode:
        raise HTTPException(status_code=503, detail=settings.maintenance_message)
    if not (settings.stripe_secret_key and settings.stripe_price_id):
        raise HTTPException(status_code=500, detail="Stripe not configured")

    account = _ensure_customer(db, user=user, settings=settings)
    stripe.api_key = settings.stripe_secret_key

    checkout = stripe.checkout.Session.create(
        mode="subscription",
        customer=account.stripe_customer_id,
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        metadata={"user_id": user.id},
    )
    return RedirectResponse(checkout["url"], status_code=303)


@router.post("/billing/portal")
def billing_portal(
    request: Request,
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="billing-portal",
        limit=settings.rate_limit_api,
        window_seconds=settings.rate_limit_window_seconds,
    )
    require_csrf(request, csrf_token)

    if not settings.billing_enabled:
        raise HTTPException(status_code=400, detail="Billing disabled")
    if settings.maintenance_mode:
        raise HTTPException(status_code=503, detail=settings.maintenance_message)
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    account = db.scalar(select(BillingAccount).where(BillingAccount.user_id == user.id))
    if not account or not account.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer on file")

    stripe.api_key = settings.stripe_secret_key
    return_url = str(request.base_url).rstrip("/") + "/billing"
    portal = stripe.billing_portal.Session.create(customer=account.stripe_customer_id, return_url=return_url)
    return RedirectResponse(portal["url"], status_code=303)


@router.get("/billing/success")
def billing_success(request: Request, user: User = Depends(require_user), db: Session = Depends(db_session)):
    request.state.user = user
    _ = db
    return templates.TemplateResponse("billing_success.html", template_context(request, title="Billing"))


@router.get("/billing/cancel")
def billing_cancel(request: Request, user: User = Depends(require_user), db: Session = Depends(db_session)):
    request.state.user = user
    _ = db
    return templates.TemplateResponse("billing_cancel.html", template_context(request, title="Billing"))


@router.post("/billing/webhook")
async def billing_webhook(request: Request, db: Session = Depends(db_session)):
    settings: Settings = request.app.state.settings
    if not settings.billing_enabled:
        raise HTTPException(status_code=400, detail="Billing disabled")
    if not (settings.stripe_secret_key and settings.stripe_webhook_secret):
        raise HTTPException(status_code=500, detail="Stripe webhook not configured")

    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    if not sig:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    stripe.api_key = settings.stripe_secret_key
    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig, secret=settings.stripe_webhook_secret)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature: {e}") from e

    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {}) or {}

    if event_type == "checkout.session.completed":
        user_id = (obj.get("metadata") or {}).get("user_id")
        customer_id = obj.get("customer")
        subscription_id = obj.get("subscription")
        if user_id and customer_id:
            account = db.scalar(select(BillingAccount).where(BillingAccount.user_id == user_id))
            if account is None:
                account = BillingAccount(user_id=user_id)
                db.add(account)
            account.stripe_customer_id = customer_id
            account.stripe_subscription_id = subscription_id
            account.subscription_status = "active"
            account.updated_at = dt.datetime.now(dt.UTC)

    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        customer_id = obj.get("customer")
        subscription_id = obj.get("id")
        status = obj.get("status", "inactive")
        period_end = obj.get("current_period_end")
        account = None
        if customer_id:
            account = db.scalar(select(BillingAccount).where(BillingAccount.stripe_customer_id == customer_id))
        if account is not None:
            account.stripe_subscription_id = subscription_id or account.stripe_subscription_id
            account.subscription_status = status or account.subscription_status
            if isinstance(period_end, int):
                account.current_period_end = dt.datetime.fromtimestamp(period_end, tz=dt.UTC)
            account.updated_at = dt.datetime.now(dt.UTC)

    return {"received": True}
