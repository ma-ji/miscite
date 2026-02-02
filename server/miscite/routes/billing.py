from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_UP

import stripe
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server.miscite.billing.ledger import credit_balance, get_or_create_account
from server.miscite.billing.stripe import auto_charge_payment_method_available, create_topup_checkout, ensure_customer
from server.miscite.core.cache import Cache
from server.miscite.core.config import Settings
from server.miscite.core.db import db_session
from server.miscite.core.models import BillingAccount, BillingTransaction, User
from server.miscite.core.rate_limit import enforce_rate_limit
from server.miscite.core.security import require_csrf, require_user
from server.miscite.web import template_context, templates

router = APIRouter()


def _success_message(raw: str | None) -> tuple[str | None, str | None]:
    key = (raw or "").strip().lower()
    if not key:
        return None, None
    if key in {"auto_charge_enabled", "auto-charge-enabled"}:
        return "Auto-charge enabled.", "auto_charge"
    if key in {"auto_charge_disabled", "auto-charge-disabled"}:
        return "Auto-charge turned off.", "auto_charge"
    if key in {"auto_charge_saved_off", "auto-charge-saved-off"}:
        return "Saved auto-charge settings (auto-charge is off).", "auto_charge"
    if key in {"auto_charge_saved", "auto-charge-saved"}:
        return "Saved auto-charge settings.", "auto_charge"
    return None, None


def _format_cents_plain(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    value = abs(int(cents)) / 100.0
    return f"{sign}{value:.2f}"


def _format_amount(cents: int) -> str:
    sign = "-" if cents < 0 else "+"
    value = abs(int(cents)) / 100.0
    return f"{sign}${value:.2f}"


def _human_datetime(ts: dt.datetime | None) -> str:
    if ts is None:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.UTC)
    return f"{ts.strftime('%b')} {ts.day}, {ts.year} at {ts.strftime('%H:%M')} UTC"


def _parse_amount_to_cents(raw: str) -> tuple[int | None, str | None]:
    value = (raw or "").strip().replace("$", "")
    if not value:
        return None, "Enter a top-up amount."
    try:
        dec = Decimal(value)
    except Exception:
        return None, "Enter a valid amount."
    if dec <= 0:
        return None, "Amount must be greater than zero."
    cents = int((dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if cents <= 0:
        return None, "Amount must be greater than zero."
    return cents, None


def _load_billing_context(
    request: Request,
    *,
    user: User,
    db: Session,
    settings: Settings,
    error: str | None = None,
    success: str | None = None,
) -> dict:
    hostname = (request.url.hostname or "").strip().lower()
    is_local_dev = hostname in {"localhost", "127.0.0.1"} or hostname.endswith(".local")

    stripe_configured = bool(settings.stripe_secret_key)
    stripe_webhook_configured = bool(settings.stripe_webhook_secret)
    stripe_ready = stripe_configured and stripe_webhook_configured

    account = db.scalar(select(BillingAccount).where(BillingAccount.user_id == user.id))
    if account is None and settings.billing_enabled:
        account = get_or_create_account(db, user_id=user.id, currency=settings.billing_currency)

    balance_cents = account.balance_cents if account else 0
    currency = account.currency if account else settings.billing_currency

    auto_charge_enabled = bool(account and account.auto_charge_enabled)
    auto_charge_threshold_cents = (
        account.auto_charge_threshold_cents if account and account.auto_charge_threshold_cents else settings.billing_auto_charge_default_threshold_cents
    )
    auto_charge_amount_cents = (
        account.auto_charge_amount_cents if account and account.auto_charge_amount_cents else settings.billing_auto_charge_default_amount_cents
    )

    billing_profile_ready = bool(account and account.stripe_customer_id)
    has_payment_method = False
    if settings.billing_enabled and stripe_configured and billing_profile_ready and account and account.stripe_customer_id:
        has_payment_method = auto_charge_payment_method_available(
            settings=settings,
            customer_id=account.stripe_customer_id,
            cache=Cache(settings=settings),
        )

    transactions = (
        db.execute(
            select(BillingTransaction)
            .where(BillingTransaction.user_id == user.id)
            .order_by(desc(BillingTransaction.created_at))
            .limit(10)
        )
        .scalars()
        .all()
    )
    transactions_payload = [
        {
            "kind": txn.kind,
            "amount_cents": txn.amount_cents,
            "amount_display": _format_amount(txn.amount_cents),
            "balance_after_cents": txn.balance_after_cents,
            "balance_after_display": f"${_format_cents_plain(txn.balance_after_cents)}",
            "created_at": txn.created_at.isoformat(),
            "created_at_human": _human_datetime(txn.created_at),
        }
        for txn in transactions
    ]

    return {
        "billing_enabled": settings.billing_enabled,
        "balance_cents": balance_cents,
        "balance_display": f"${_format_cents_plain(balance_cents)}",
        "currency": currency,
        "min_charge_cents": settings.billing_min_charge_cents,
        "min_charge_display": f"${_format_cents_plain(settings.billing_min_charge_cents)}",
        "auto_charge_enabled": auto_charge_enabled,
        "auto_charge_threshold_cents": auto_charge_threshold_cents,
        "auto_charge_threshold_display": f"${_format_cents_plain(auto_charge_threshold_cents)}",
        "auto_charge_threshold_value": f"{auto_charge_threshold_cents / 100:.2f}",
        "auto_charge_amount_cents": auto_charge_amount_cents,
        "auto_charge_amount_display": f"${_format_cents_plain(auto_charge_amount_cents)}",
        "auto_charge_amount_value": f"{auto_charge_amount_cents / 100:.2f}",
        "auto_charge_last_error": account.auto_charge_last_error if account else None,
        "can_open_portal": bool(settings.stripe_secret_key),
        "stripe_configured": stripe_configured,
        "stripe_webhook_configured": stripe_webhook_configured,
        "stripe_ready": stripe_ready,
        "billing_profile_ready": billing_profile_ready,
        "has_payment_method": has_payment_method,
        "is_local_dev": is_local_dev,
        "transactions": transactions_payload,
        "billing_error": error,
        "billing_success": success,
    }


@router.get("/billing")
def billing_page(
    request: Request,
    success: str = "",
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings

    success_message, success_scope = _success_message(success)
    return templates.TemplateResponse(
        "billing.html",
        template_context(
            request,
            title="Billing",
            **_load_billing_context(request, user=user, db=db, settings=settings, success=success_message),
            auto_charge_success=success_message if success_scope == "auto_charge" else None,
        ),
    )


@router.post("/billing/topup")
def billing_topup(
    request: Request,
    amount: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="billing-topup",
        limit=settings.rate_limit_api,
        window_seconds=settings.rate_limit_window_seconds,
    )
    require_csrf(request, csrf_token)

    if not settings.billing_enabled:
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error="Billing disabled"),
            ),
        )
    if settings.maintenance_mode:
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error=settings.maintenance_message),
            ),
        )
    if not settings.stripe_secret_key:
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error="Stripe is not configured."),
            ),
        )
    if not settings.stripe_webhook_secret:
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(
                    request,
                    user=user,
                    db=db,
                    settings=settings,
                    error="Stripe webhook is not configured; top-ups cannot be credited.",
                ),
            ),
        )

    amount_cents, error = _parse_amount_to_cents(amount)
    if error:
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error=error),
            ),
        )
    if amount_cents is None or amount_cents < settings.billing_min_charge_cents:
        error = f"Minimum top-up is ${_format_cents_plain(settings.billing_min_charge_cents)}."
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error=error),
            ),
        )

    account = ensure_customer(db, user=user, settings=settings)
    db.add(account)
    db.commit()
    checkout = create_topup_checkout(
        settings=settings,
        account=account,
        user_id=user.id,
        amount_cents=amount_cents,
    )
    return RedirectResponse(checkout["url"], status_code=303)


@router.post("/billing/auto-charge")
def billing_auto_charge(
    request: Request,
    enabled: str = Form(""),
    threshold: str = Form(""),
    amount: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(db_session),
):
    request.state.user = user
    settings: Settings = request.app.state.settings
    enforce_rate_limit(
        request,
        settings=settings,
        key="billing-auto-charge",
        limit=settings.rate_limit_api,
        window_seconds=settings.rate_limit_window_seconds,
    )
    require_csrf(request, csrf_token)

    if not settings.billing_enabled:
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error="Billing disabled"),
            ),
        )
    if settings.maintenance_mode:
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error=settings.maintenance_message),
            ),
        )

    account = get_or_create_account(db, user_id=user.id, currency=settings.billing_currency)

    was_enabled = bool(account.auto_charge_enabled)
    enable = (enabled or "").strip().lower() in {"true", "1", "yes", "on"}

    threshold_cents, threshold_err = _parse_amount_to_cents(threshold)
    amount_cents, amount_err = _parse_amount_to_cents(amount)
    if threshold_err or amount_err:
        error = threshold_err or amount_err or "Enter valid auto-charge values."
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error=error),
                auto_charge_error=error,
            ),
        )

    resolved_threshold_cents = threshold_cents or settings.billing_auto_charge_default_threshold_cents
    resolved_amount_cents = amount_cents or settings.billing_auto_charge_default_amount_cents
    if resolved_amount_cents < settings.billing_min_charge_cents:
        error = f"Auto-charge amount must be at least ${_format_cents_plain(settings.billing_min_charge_cents)}."
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error=error),
                auto_charge_error=error,
            ),
        )

    account.auto_charge_threshold_cents = int(resolved_threshold_cents)
    account.auto_charge_amount_cents = int(resolved_amount_cents)
    account.updated_at = dt.datetime.now(dt.UTC)
    db.add(account)
    db.commit()

    if not enable:
        account.auto_charge_enabled = False
        account.auto_charge_last_error = None
        account.auto_charge_in_flight = False
        account.auto_charge_in_flight_at = None
        account.auto_charge_in_flight_amount_cents = 0
        account.auto_charge_in_flight_idempotency_key = None
        account.auto_charge_in_flight_payment_intent_id = None
        account.updated_at = dt.datetime.now(dt.UTC)
        db.commit()
        success = "auto_charge_disabled" if was_enabled else "auto_charge_saved_off"
        return RedirectResponse(f"/billing?success={success}#auto-charge", status_code=303)

    if not settings.stripe_secret_key:
        error = "Stripe is not configured in this environment."
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error=error),
                auto_charge_error=error,
            ),
        )
    if not settings.stripe_webhook_secret:
        error = "Stripe webhook is not configured in this environment."
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error=error),
                auto_charge_error=error,
            ),
        )

    if was_enabled:
        account.auto_charge_enabled = True
        account.auto_charge_last_error = None
        account.updated_at = dt.datetime.now(dt.UTC)
        db.commit()
        return RedirectResponse("/billing?success=auto_charge_saved#auto-charge", status_code=303)

    if not account.stripe_customer_id:
        try:
            account = ensure_customer(db, user=user, settings=settings)
            db.add(account)
            db.commit()
        except Exception:
            db.rollback()
            error = "Unable to create a Stripe customer for this account."
            return templates.TemplateResponse(
                "billing.html",
                template_context(
                    request,
                    title="Billing",
                    **_load_billing_context(request, user=user, db=db, settings=settings, error=error),
                    auto_charge_error=error,
                ),
            )

    if not auto_charge_payment_method_available(
        settings=settings,
        customer_id=account.stripe_customer_id,
        cache=Cache(settings=settings),
    ):
        error = "Add a payment method (complete a top-up or use the portal) before enabling auto-charge."
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error=error),
                auto_charge_error=error,
            ),
        )

    account.auto_charge_enabled = True
    account.auto_charge_last_error = None
    account.updated_at = dt.datetime.now(dt.UTC)
    db.commit()
    success = "auto_charge_saved" if was_enabled else "auto_charge_enabled"
    return RedirectResponse(f"/billing?success={success}#auto-charge", status_code=303)


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
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error="Billing disabled"),
            ),
        )
    if settings.maintenance_mode:
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error=settings.maintenance_message),
            ),
        )
    if not settings.stripe_secret_key:
        return templates.TemplateResponse(
            "billing.html",
            template_context(
                request,
                title="Billing",
                **_load_billing_context(request, user=user, db=db, settings=settings, error="Stripe is not configured."),
            ),
        )

    account = ensure_customer(db, user=user, settings=settings)
    db.add(account)
    db.commit()

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


def _already_recorded(
    db: Session,
    *,
    session_id: str | None = None,
    payment_intent_id: str | None = None,
) -> bool:
    if session_id:
        existing = db.scalar(
            select(BillingTransaction.id).where(BillingTransaction.stripe_checkout_session_id == session_id)
        )
        if existing:
            return True
    if payment_intent_id:
        existing = db.scalar(
            select(BillingTransaction.id).where(BillingTransaction.stripe_payment_intent_id == payment_intent_id)
        )
        if existing:
            return True
    return False


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
        if obj.get("mode") != "payment":
            return {"received": True}
        metadata = obj.get("metadata") or {}
        user_id = metadata.get("user_id")
        amount_total = obj.get("amount_total")
        currency = (obj.get("currency") or settings.billing_currency).lower()
        session_id = obj.get("id")
        payment_intent_id = obj.get("payment_intent")
        customer_id = obj.get("customer")
        if not user_id or amount_total is None:
            return {"received": True}
        if _already_recorded(db, session_id=session_id):
            return {"received": True}

        account = get_or_create_account(db, user_id=user_id, currency=currency)
        if customer_id and not account.stripe_customer_id:
            account.stripe_customer_id = customer_id

        credit_balance(
            db,
            account=account,
            amount_cents=int(amount_total),
            currency=currency,
            kind="topup",
            note="Stripe top-up",
            stripe_checkout_session_id=session_id,
            stripe_payment_intent_id=payment_intent_id,
        )
        account.auto_charge_last_error = None
        db.add(account)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"received": True}

        if customer_id and payment_intent_id:
            try:
                intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                payment_method = intent.get("payment_method")
                if payment_method:
                    stripe.Customer.modify(
                        customer_id,
                        invoice_settings={"default_payment_method": payment_method},
                    )
            except Exception:
                pass

    elif event_type == "payment_intent.succeeded":
        metadata = obj.get("metadata") or {}
        if metadata.get("flow") != "auto_charge":
            return {"received": True}
        user_id = metadata.get("user_id")
        if not user_id:
            return {"received": True}
        payment_intent_id = obj.get("id")
        if _already_recorded(db, payment_intent_id=payment_intent_id):
            return {"received": True}
        amount_received = obj.get("amount_received") or obj.get("amount")
        currency = (obj.get("currency") or settings.billing_currency).lower()
        customer_id = obj.get("customer")
        if amount_received is None:
            return {"received": True}

        account = get_or_create_account(db, user_id=user_id, currency=currency)
        if customer_id and not account.stripe_customer_id:
            account.stripe_customer_id = customer_id

        credit_balance(
            db,
            account=account,
            amount_cents=int(amount_received),
            currency=currency,
            kind="auto_charge",
            note="Auto-charge",
            stripe_payment_intent_id=payment_intent_id,
        )
        account.auto_charge_last_error = None
        account.auto_charge_in_flight = False
        account.auto_charge_in_flight_at = None
        account.auto_charge_in_flight_amount_cents = 0
        account.auto_charge_in_flight_idempotency_key = None
        account.auto_charge_in_flight_payment_intent_id = None
        db.add(account)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"received": True}

    elif event_type == "payment_intent.payment_failed":
        metadata = obj.get("metadata") or {}
        if metadata.get("flow") != "auto_charge":
            return {"received": True}
        user_id = metadata.get("user_id")
        if not user_id:
            return {"received": True}
        account = db.scalar(select(BillingAccount).where(BillingAccount.user_id == user_id))
        if account is None:
            return {"received": True}
        error = (obj.get("last_payment_error") or {}).get("message") or "Auto-charge failed."
        account.auto_charge_last_error = str(error)
        account.auto_charge_in_flight = False
        account.auto_charge_in_flight_at = None
        account.auto_charge_in_flight_amount_cents = 0
        account.auto_charge_in_flight_idempotency_key = None
        account.auto_charge_in_flight_payment_intent_id = None
        db.add(account)
        db.commit()

    return {"received": True}
