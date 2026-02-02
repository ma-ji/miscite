from __future__ import annotations

import datetime as dt

import stripe
from sqlalchemy import select
from sqlalchemy.orm import Session

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


def create_auto_charge_payment_intent(
    *,
    settings: Settings,
    account: BillingAccount,
    amount_cents: int,
) -> stripe.PaymentIntent:
    stripe.api_key = settings.stripe_secret_key
    customer = stripe.Customer.retrieve(account.stripe_customer_id)
    invoice_settings = customer.get("invoice_settings") or {}
    payment_method = invoice_settings.get("default_payment_method") or customer.get("default_source")
    if not payment_method:
        raise RuntimeError("No default payment method on file for auto-charge.")

    return stripe.PaymentIntent.create(
        amount=int(amount_cents),
        currency=settings.billing_currency,
        customer=account.stripe_customer_id,
        payment_method=payment_method,
        off_session=True,
        confirm=True,
        metadata={"user_id": account.user_id, "flow": "auto_charge"},
    )
