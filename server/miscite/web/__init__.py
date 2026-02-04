from __future__ import annotations

import re
import json
from urllib.parse import urlsplit
from urllib.parse import urlparse

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from server.miscite.core.security import get_csrf_cookie

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


def pretty_json(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return ""


templates.env.filters["pretty_json"] = pretty_json


def public_origin(request: Request) -> str:
    settings = request.app.state.settings

    scheme = request.url.scheme or "http"
    host = request.headers.get("host") or request.url.netloc

    if settings.trust_proxy:
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        forwarded_host = request.headers.get("x-forwarded-host", "")

        if forwarded_proto:
            scheme = forwarded_proto.split(",")[0].strip() or scheme
        if forwarded_host:
            host = forwarded_host.split(",")[0].strip() or host

    if host:
        return f"{scheme}://{host}".rstrip("/")

    base = str(request.base_url).rstrip("/")
    if base:
        return base

    parsed = urlsplit(str(request.url))
    netloc = parsed.netloc or host
    if netloc:
        return f"{scheme}://{netloc}".rstrip("/")
    return ""


def template_context(request: Request, **extra):
    settings = request.app.state.settings
    path = request.url.path or "/"
    origin = public_origin(request)
    canonical_url = f"{origin}{path}" if origin else path

    meta_description = extra.get("meta_description")
    if not meta_description:
        if path == "/":
            meta_description = (
                "Audit-ready citation checks for journals, labs, and research teams. "
                "Upload PDF/DOCX manuscripts, resolve references, and flag missing, retracted, or risky citations."
            )
        else:
            meta_description = (
                "Audit-ready citation checks with evidence-first reports."
            )

    robots = extra.get("robots")
    if not robots:
        robots = "index, follow" if path == "/" else "noindex, nofollow"

    return {
        "request": request,
        "current_user": getattr(request.state, "user", None),
        "csrf_token": get_csrf_cookie(request) or "",
        "record_estimate": "455M+",
        "access_token_days": settings.access_token_days,
        "csp_nonce": getattr(request.state, "csp_nonce", ""),
        "maintenance_mode": settings.maintenance_mode,
        "maintenance_message": settings.maintenance_message,
        "public_origin": origin,
        "sample_report_url": settings.sample_report_url,
        "canonical_url": canonical_url,
        "meta_description": meta_description,
        "robots": robots,
        **extra,
    }
