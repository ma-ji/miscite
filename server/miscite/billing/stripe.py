from __future__ import annotations

import datetime as dt

import stripe
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.miscite.core.cache import Cache
from server.miscite.core.config import Settings
from server.miscite.core.models import BillingAccount, User


def ensure_customer(db: Session, *, user: User, settings: Settings) -> BillingAccount:
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


def create_topup_checkout(
    *,
    settings: Settings,
    account: BillingAccount,
    user_id: str,
    amount_cents: int,
) -> stripe.checkout.Session:
    stripe.api_key = settings.stripe_secret_key
    return stripe.checkout.Session.create(
        mode="payment",
        customer=account.stripe_customer_id,
        line_items=[
            {
                "price_data": {
                    "currency": settings.billing_currency,
                    "product_data": {"name": "miscite balance top-up"},
                    "unit_amount": int(amount_cents),
                },
                "quantity": 1,
            }
        ],
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        metadata={"user_id": user_id, "flow": "topup", "amount_cents": str(amount_cents)},
        payment_intent_data={
            "setup_future_usage": "off_session",
            "metadata": {"user_id": user_id, "flow": "topup"},
        },
    )


def _resolve_auto_charge_payment_method_id(*, customer: dict, customer_id: str) -> str | None:
    invoice_settings = customer.get("invoice_settings") or {}
    payment_method = invoice_settings.get("default_payment_method") or customer.get("default_source")
    if isinstance(payment_method, dict):
        payment_method = payment_method.get("id")
    if payment_method:
        return str(payment_method)
    try:
        methods = stripe.PaymentMethod.list(customer=customer_id, type="card", limit=1)
        data = methods.get("data") if hasattr(methods, "get") else getattr(methods, "data", None)
        if not data:
            return None
        first = data[0]
        if isinstance(first, dict):
            return first.get("id")
        return getattr(first, "id", None)
    except Exception:
        return None


def auto_charge_payment_method_available(
    *,
    settings: Settings,
    customer_id: str,
    cache: Cache | None = None,
) -> bool:
    customer_id = (customer_id or "").strip()
    if not customer_id:
        return False
    if cache is not None:
        hit, payload = cache.get_json("stripe", [customer_id, "auto_charge_payment_method_available"])
        if hit and isinstance(payload, dict):
            cached = payload.get("has_payment_method")
            if isinstance(cached, bool):
                return cached

    stripe.api_key = settings.stripe_secret_key
    try:
        customer = stripe.Customer.retrieve(customer_id)
        resolved = _resolve_auto_charge_payment_method_id(customer=customer, customer_id=customer_id)
        has_payment_method = bool(resolved)
    except Exception:
        has_payment_method = False

    if cache is not None:
        cache.set_json(
            "stripe",
            [customer_id, "auto_charge_payment_method_available"],
            {"has_payment_method": has_payment_method},
            ttl_seconds=120,
        )
    return has_payment_method


def create_auto_charge_payment_intent(
    *,
    settings: Settings,
    account: BillingAccount,
    amount_cents: int,
    idempotency_key: str | None = None,
) -> stripe.PaymentIntent:
    stripe.api_key = settings.stripe_secret_key
    customer = stripe.Customer.retrieve(account.stripe_customer_id)
    payment_method = _resolve_auto_charge_payment_method_id(customer=customer, customer_id=account.stripe_customer_id)
    if not payment_method:
        raise RuntimeError("No default payment method on file for auto-charge.")

    return stripe.PaymentIntent.create(
        amount=int(amount_cents),
        currency=settings.billing_currency,
        customer=account.stripe_customer_id,
        payment_method=str(payment_method),
        off_session=True,
        confirm=True,
        metadata={"user_id": account.user_id, "flow": "auto_charge"},
        idempotency_key=idempotency_key,
    )
