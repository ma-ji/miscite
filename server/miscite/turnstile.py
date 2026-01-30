from __future__ import annotations

import requests

from server.miscite.config import Settings


def verify_turnstile(
    settings: Settings,
    *,
    token: str,
    remote_ip: str | None = None,
) -> tuple[bool, str | None]:
    if not settings.turnstile_site_key or not settings.turnstile_secret_key:
        return False, "Turnstile is not configured."
    if not token:
        return False, "Turnstile token missing."

    data = {
        "secret": settings.turnstile_secret_key,
        "response": token,
    }
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        resp = requests.post(settings.turnstile_verify_url, data=data, timeout=settings.api_timeout_seconds)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return False, "Turnstile verification failed."

    if payload.get("success") is True:
        return True, None
    return False, "Turnstile verification failed."
