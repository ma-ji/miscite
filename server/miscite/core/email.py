from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import requests

from server.miscite.core.config import Settings

_BRAND_COLOR = "#990000"
_TEXT_COLOR = "#072332"
_MUTED_COLOR = "#5f6b72"
_SURFACE_COLOR = "#ffffff"
_BG_COLOR = "#f8efe2"


def _public_origin(settings: Settings) -> str:
    return (settings.public_origin or "").strip().rstrip("/")


def _join_public_url(settings: Settings, path: str) -> str:
    origin = _public_origin(settings)
    if not origin:
        return path
    return f"{origin}/{path.lstrip('/')}"


def _format_money(amount_cents: int, currency: str) -> str:
    sign = "-" if amount_cents < 0 else ""
    value = abs(int(amount_cents)) / 100.0
    label = (currency or "usd").upper()
    if label == "USD":
        return f"{sign}${value:.2f}"
    return f"{sign}{value:.2f} {label}"


def _format_sender(sender: str) -> str:
    sender = (sender or "").strip()
    if not sender:
        return sender
    if "<" in sender and ">" in sender:
        start = sender.find("<") + 1
        end = sender.find(">", start)
        email = sender[start:end].strip() or sender
    else:
        email = sender
    return f"Miscite.Review <{email}>"


def _email_shell(*, title: str, preheader: str, body_html: str, footer_html: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
  </head>
  <body style="margin:0; padding:0; background:{_BG_COLOR}; color:{_TEXT_COLOR};">
    <span style="display:none; font-size:1px; color:{_BG_COLOR}; line-height:1px; max-height:0; max-width:0; opacity:0; overflow:hidden;">
      {preheader}
    </span>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{_BG_COLOR}; padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="width:100%; max-width:600px; background:{_SURFACE_COLOR}; border-radius:16px; overflow:hidden; box-shadow:0 12px 30px rgba(7, 35, 50, 0.12);">
            <tr>
              <td style="padding:18px 24px; background:{_BRAND_COLOR}; color:#ffffff; font-family:Arial, sans-serif; font-size:16px; font-weight:600; letter-spacing:0.02em;">
                Miscite.Review
              </td>
            </tr>
            <tr>
              <td style="padding:28px 28px 12px; font-family:Arial, sans-serif; font-size:16px; line-height:1.6; color:{_TEXT_COLOR};">
                <h1 style="margin:0 0 12px; font-size:22px; line-height:1.3; color:{_TEXT_COLOR};">{title}</h1>
                {body_html}
              </td>
            </tr>
            <tr>
              <td style="padding:0 28px 24px; font-family:Arial, sans-serif; font-size:12px; line-height:1.5; color:{_MUTED_COLOR};">
                {footer_html}
              </td>
            </tr>
          </table>
          <p style="margin:16px 0 0; font-family:Arial, sans-serif; font-size:12px; color:{_MUTED_COLOR};">
            If you did not request this email, you can safely ignore it.
          </p>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


@dataclass
class MailgunClient:
    api_key: str
    domain: str
    sender: str
    base_url: str
    timeout_seconds: float

    def send_message(self, *, to_email: str, subject: str, text: str, html: str | None = None) -> None:
        if not self.api_key or not self.domain or not self.sender:
            raise ValueError("Mailgun settings are missing.")
        url = f"{self.base_url.rstrip('/')}/{self.domain}/messages"
        data = {
            "from": _format_sender(self.sender),
            "to": to_email,
            "subject": subject,
            "text": text,
        }
        if html:
            data["html"] = html
        resp = requests.post(
            url,
            auth=("api", self.api_key),
            data=data,
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()


def send_login_code_email(settings: Settings, *, to_email: str, code: str) -> None:
    ttl_minutes = settings.login_code_ttl_minutes
    subject = "Your Miscite.Review sign-in code"
    text = (
        "Use this code to sign in to Miscite.Review:\n\n"
        f"{code}\n\n"
        f"This code expires in {ttl_minutes} minutes."
    )
    html = _email_shell(
        title="Sign-in code",
        preheader=f"Your sign-in code expires in {ttl_minutes} minutes.",
        body_html=(
            "<p>Use this code to sign in to your Miscite.Review workspace:</p>"
            f"<div style=\"margin:18px 0; padding:14px 18px; border-radius:12px; background:#f5e3cc; font-size:22px; font-weight:600; letter-spacing:0.14em; text-align:center; color:{_TEXT_COLOR};\">{code}</div>"
            f"<p style=\"margin:0; color:{_MUTED_COLOR};\">This code expires in {ttl_minutes} minutes.</p>"
        ),
        footer_html=(
            "<p style=\"margin:0;\">Need help? Reply to this email and we will get you sorted.</p>"
        ),
    )
    client = MailgunClient(
        api_key=settings.mailgun_api_key,
        domain=settings.mailgun_domain,
        sender=settings.mailgun_sender,
        base_url=settings.mailgun_base_url,
        timeout_seconds=settings.api_timeout_seconds,
    )
    client.send_message(to_email=to_email, subject=subject, text=text, html=html)


def send_access_token_email(
    settings: Settings,
    *,
    to_email: str,
    token: str,
    job_id: str,
    filename: str,
    expires_at: dt.datetime | None,
) -> None:
    expires_label = "No expiration"
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=dt.UTC)
        expires_label = (
            f"{expires_at.strftime('%b')} {expires_at.day}, {expires_at.year} at {expires_at.strftime('%H:%M')} UTC"
        )
    subject = "Your Miscite.Review report is ready"
    report_url = _join_public_url(settings, f"/reports/{token}")
    access_url = _join_public_url(settings, "/reports/access")
    text = (
        "Your Miscite.Review report is ready.\n\n"
        "Access token (case-sensitive):\n"
        f"{token}\n\n"
        "Open the report with:\n"
        f"{report_url}\n"
        "Or enter the token here:\n"
        f"{access_url}\n\n"
        f"Job: {filename} ({job_id})\n"
        f"Expires: {expires_label}\n"
        "Reports are deleted after the access token expires."
    )
    html = _email_shell(
        title="Report ready",
        preheader="Your report is ready to view and share.",
        body_html=(
            "<p>Your report is ready to review and share.</p>"
            f"<p style=\"margin:18px 0 6px; color:{_MUTED_COLOR};\">Access token (case-sensitive)</p>"
            f"<div style=\"margin:0 0 18px; padding:12px 16px; border-radius:12px; background:#f5e3cc; font-size:18px; font-weight:600; letter-spacing:0.06em; color:{_TEXT_COLOR};\">{token}</div>"
            "<p style=\"margin:0 0 12px;\">Open the report with:</p>"
            f"<div style=\"margin:0 0 16px; padding:10px 14px; border-radius:10px; background:#f0f2f3; font-family:Arial, sans-serif; font-size:13px; color:{_TEXT_COLOR};\">{report_url}</div>"
            "<p style=\"margin:0 0 6px;\">Or enter the token here:</p>"
            f"<div style=\"margin:0 0 18px; padding:10px 14px; border-radius:10px; background:#f0f2f3; font-family:Arial, sans-serif; font-size:13px; color:{_TEXT_COLOR};\">{access_url}</div>"
            f"<p style=\"margin:0; color:{_MUTED_COLOR};\">Job: {filename} ({job_id})</p>"
            f"<p style=\"margin:4px 0 0; color:{_MUTED_COLOR};\">Expires: {expires_label}</p>"
        ),
        footer_html=(
            "<p style=\"margin:0;\">Reports are deleted after the access token expires. "
            "You can adjust expiration or renew the token from the report page.</p>"
        ),
    )
    client = MailgunClient(
        api_key=settings.mailgun_api_key,
        domain=settings.mailgun_domain,
        sender=settings.mailgun_sender,
        base_url=settings.mailgun_base_url,
        timeout_seconds=settings.api_timeout_seconds,
    )
    client.send_message(to_email=to_email, subject=subject, text=text, html=html)


def send_billing_receipt_email(
    settings: Settings,
    *,
    to_email: str,
    amount_cents: int,
    currency: str,
    kind: str,
    receipt_url: str | None,
    payment_intent_id: str | None,
    occurred_at: dt.datetime | None,
) -> None:
    amount_label = _format_money(amount_cents, currency)
    flow_label = "Top-up" if kind == "topup" else "Auto-charge"
    subject = f"Receipt for your Miscite.Review {flow_label.lower()}"
    when_label = ""
    if occurred_at:
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=dt.UTC)
        when_label = f"{occurred_at.strftime('%b')} {occurred_at.day}, {occurred_at.year} at {occurred_at.strftime('%H:%M')} UTC"
    billing_url = _join_public_url(settings, "/billing")

    lines = [
        f"{flow_label} receipt for Miscite.Review",
        f"Amount: {amount_label}",
    ]
    if when_label:
        lines.append(f"Date: {when_label}")
    if payment_intent_id:
        lines.append(f"Payment reference: {payment_intent_id}")
    if receipt_url:
        lines.append(f"Stripe receipt: {receipt_url}")
    lines.append(f"Billing page: {billing_url}")

    html_receipt = (
        f"<p style=\"margin:0 0 12px;\">We received your {flow_label.lower()} payment.</p>"
        f"<p style=\"margin:0 0 6px;\"><strong>Amount:</strong> {amount_label}</p>"
    )
    if when_label:
        html_receipt += f"<p style=\"margin:0 0 6px;\"><strong>Date:</strong> {when_label}</p>"
    if payment_intent_id:
        html_receipt += (
            f"<p style=\"margin:0 0 6px;\"><strong>Payment reference:</strong> {payment_intent_id}</p>"
        )
    if receipt_url:
        html_receipt += (
            f"<p style=\"margin:0 0 6px;\"><a href=\"{receipt_url}\" style=\"color:{_BRAND_COLOR};\">View Stripe receipt</a></p>"
        )
    html_receipt += (
        f"<p style=\"margin:12px 0 0;\"><a href=\"{billing_url}\" style=\"color:{_BRAND_COLOR};\">Open billing</a></p>"
    )

    html = _email_shell(
        title=f"{flow_label} receipt",
        preheader=f"{flow_label} receipt for {amount_label}.",
        body_html=html_receipt,
        footer_html="<p style=\"margin:0;\">Keep this receipt for your records.</p>",
    )
    text = "\n".join(lines)
    client = MailgunClient(
        api_key=settings.mailgun_api_key,
        domain=settings.mailgun_domain,
        sender=settings.mailgun_sender,
        base_url=settings.mailgun_base_url,
        timeout_seconds=settings.api_timeout_seconds,
    )
    client.send_message(to_email=to_email, subject=subject, text=text, html=html)
