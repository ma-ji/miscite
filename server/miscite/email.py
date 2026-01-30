from __future__ import annotations

from dataclasses import dataclass

import requests

from server.miscite.config import Settings


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
            "from": self.sender,
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
    subject = "Your miscite sign-in code"
    text = (
        "Use this code to sign in to miscite:\n\n"
        f"{code}\n\n"
        f"This code expires in {ttl_minutes} minutes."
    )
    html = (
        "<p>Use this code to sign in to miscite:</p>"
        f"<p style=\"font-size:20px; font-weight:600; letter-spacing:0.08em\">{code}</p>"
        f"<p>This code expires in {ttl_minutes} minutes.</p>"
    )
    client = MailgunClient(
        api_key=settings.mailgun_api_key,
        domain=settings.mailgun_domain,
        sender=settings.mailgun_sender,
        base_url=settings.mailgun_base_url,
        timeout_seconds=settings.api_timeout_seconds,
    )
    client.send_message(to_email=to_email, subject=subject, text=text, html=html)
