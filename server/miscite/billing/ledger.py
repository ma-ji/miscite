from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from server.miscite.core.config import Settings
from server.miscite.core.models import BillingAccount, BillingTransaction


@dataclass(frozen=True)
class BillingResult:
    status: str
    error: str | None
    balance_cents: int | None


def get_or_create_account(db: Session, *, user_id: str, currency: str) -> BillingAccount:
    account = db.scalar(select(BillingAccount).where(BillingAccount.user_id == user_id))
    if account is None:
        account = BillingAccount(
            user_id=user_id,
            currency=currency,
            subscription_status="inactive",
            updated_at=dt.datetime.now(dt.UTC),
        )
        db.add(account)
        db.flush()
    if not account.currency:
        account.currency = currency
    return account


def _apply_transaction(
    db: Session,
    *,
    account: BillingAccount,
    kind: str,
    amount_cents: int,
    currency: str,
    job_id: str | None = None,
    note: str | None = None,
    stripe_checkout_session_id: str | None = None,
    stripe_payment_intent_id: str | None = None,
) -> BillingTransaction:
    account.balance_cents = int(account.balance_cents or 0) + int(amount_cents)
    account.currency = currency or account.currency or "usd"
    account.updated_at = dt.datetime.now(dt.UTC)

    txn = BillingTransaction(
        user_id=account.user_id,
        job_id=job_id,
        kind=kind,
        amount_cents=amount_cents,
        currency=account.currency,
        balance_after_cents=account.balance_cents,
        stripe_checkout_session_id=stripe_checkout_session_id,
        stripe_payment_intent_id=stripe_payment_intent_id,
        note=note,
        created_at=dt.datetime.now(dt.UTC),
    )
    db.add(txn)
    return txn


def credit_balance(
    db: Session,
    *,
    account: BillingAccount,
    amount_cents: int,
    currency: str,
    kind: str = "topup",
    note: str | None = None,
    stripe_checkout_session_id: str | None = None,
    stripe_payment_intent_id: str | None = None,
) -> BillingTransaction:
    return _apply_transaction(
        db,
        account=account,
        kind=kind,
        amount_cents=abs(int(amount_cents)),
        currency=currency,
        note=note,
        stripe_checkout_session_id=stripe_checkout_session_id,
        stripe_payment_intent_id=stripe_payment_intent_id,
    )


def debit_balance(
    db: Session,
    *,
    account: BillingAccount,
    amount_cents: int,
    currency: str,
    job_id: str | None = None,
    kind: str = "usage",
    note: str | None = None,
) -> BillingTransaction:
    return _apply_transaction(
        db,
        account=account,
        kind=kind,
        amount_cents=-abs(int(amount_cents)),
        currency=currency,
        job_id=job_id,
        note=note,
    )


def apply_usage_charge(
    db: Session,
    *,
    settings: Settings,
    user_id: str,
    job_id: str,
    amount_cents: int,
    currency: str,
) -> BillingResult:
    if amount_cents <= 0:
        return BillingResult(status="skipped", error=None, balance_cents=None)

    account = get_or_create_account(db, user_id=user_id, currency=currency)
    try:
        debit_balance(
            db,
            account=account,
            amount_cents=amount_cents,
            currency=currency,
            job_id=job_id,
            kind="usage",
            note="LLM usage charge",
        )
        return BillingResult(status="charged", error=None, balance_cents=account.balance_cents)
    except Exception as e:
        return BillingResult(status="failed", error=str(e), balance_cents=account.balance_cents)
