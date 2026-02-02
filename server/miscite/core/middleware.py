from __future__ import annotations

import secrets
from collections.abc import Iterable

from fastapi import Request
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from server.miscite.core.config import Settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next):
        request.state.csp_nonce = secrets.token_urlsafe(16)
        response = await call_next(request)

        nonce = getattr(request.state, "csp_nonce", "")
        csp_parts = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}' https://challenges.cloudflare.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data:",
            "connect-src 'self' https://challenges.cloudflare.com",
            "frame-src https://challenges.cloudflare.com",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            # Stripe Checkout / Customer Portal is launched via redirects from same-origin POSTs.
            # Browsers enforce CSP `form-action` on redirect chains, so allow Stripe here.
            "form-action 'self' https://checkout.stripe.com https://billing.stripe.com https://api.stripe.com",
        ]
        if self._settings.cookie_secure:
            csp_parts.append("upgrade-insecure-requests")

        response.headers.setdefault("Content-Security-Policy", "; ".join(csp_parts))
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), display-capture=()",
        )
        if self._settings.cookie_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app, *, max_body_bytes: int, include_paths: Iterable[str] | None = None
    ) -> None:
        super().__init__(app)
        self._max_body_bytes = max_body_bytes
        self._include_paths = tuple(include_paths or [])

    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            if not self._include_paths or any(
                request.url.path.startswith(p) for p in self._include_paths
            ):
                content_length = request.headers.get("content-length")
                if content_length:
                    try:
                        size = int(content_length)
                    except ValueError:
                        return PlainTextResponse(
                            "Invalid Content-Length header.", status_code=400
                        )
                    if size > self._max_body_bytes:
                        return PlainTextResponse(
                            "Request body too large.", status_code=413
                        )
        return await call_next(request)
