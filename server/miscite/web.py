from __future__ import annotations

import re
from urllib.parse import urlparse

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from server.miscite.security import get_csrf_cookie

templates = Jinja2Templates(directory="server/miscite/templates")


_DEEP_CITE_RE = re.compile(r"\[R(?P<num>\d{1,4})\]")
_SAFE_URL_SCHEMES = {"http", "https"}


def deep_cite_links(text: str | None) -> Markup:
    if not text:
        return Markup("")
    out: list[Markup] = []
    last = 0
    for m in _DEEP_CITE_RE.finditer(text):
        out.append(escape(text[last : m.start()]))
        num = m.group("num")
        rid = f"R{num}"
        out.append(Markup(f'<a href="#da-ref-{rid}" class="miscite-mono">[{rid}]</a>'))
        last = m.end()
    out.append(escape(text[last:]))
    return Markup("").join(out)


templates.env.filters["da_cite"] = deep_cite_links


def safe_url(value: str | None) -> str:
    if not value:
        return ""
    url = str(value).strip()
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    if parsed.scheme.lower() in _SAFE_URL_SCHEMES and parsed.netloc:
        return url
    return ""


templates.env.filters["safe_url"] = safe_url


def template_context(request: Request, **extra):
    settings = request.app.state.settings
    return {
        "request": request,
        "current_user": getattr(request.state, "user", None),
        "csrf_token": get_csrf_cookie(request) or "",
        "record_estimate": "250M+",
        "access_token_days": settings.access_token_days,
        "csp_nonce": getattr(request.state, "csp_nonce", ""),
        "maintenance_mode": settings.maintenance_mode,
        "maintenance_message": settings.maintenance_message,
        **extra,
    }
