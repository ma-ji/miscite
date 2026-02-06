from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import urlsplit
from urllib.parse import urlparse

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from server.miscite.core.security import get_csrf_cookie

templates = Jinja2Templates(directory="server/miscite/templates")


_DEEP_CITE_RE = re.compile(r"\[R(?P<num>\d{1,4})\]")
_SAFE_URL_SCHEMES = {"http", "https"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_DEFAULT_ROBOTS_INDEX = "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1"
_DEFAULT_ROBOTS_NOINDEX = "noindex, nofollow, noarchive"
_DEFAULT_META_KEYWORDS = (
    "citation checker, manuscript citation analysis, reference validation, "
    "retracted citation detection, predatory journal detection, academic integrity"
)

SEO_SITEMAP_ENTRIES: tuple[dict[str, str], ...] = (
    {"path": "/", "changefreq": "weekly", "priority": "1.0"},
    {"path": "/login", "changefreq": "monthly", "priority": "0.6"},
    {"path": "/reports/access", "changefreq": "monthly", "priority": "0.5"},
)

_SEO_PATH_DEFAULTS: dict[str, dict[str, str]] = {
    "/": {
        "meta_description": (
            "Audit-ready citation checks for journals, labs, and research teams. "
            "Upload PDF/DOCX manuscripts, resolve references, and flag missing, retracted, or risky citations."
        ),
        "meta_keywords": _DEFAULT_META_KEYWORDS,
        "robots": _DEFAULT_ROBOTS_INDEX,
        "twitter_card": "summary_large_image",
        "og_type": "website",
    },
    "/login": {
        "meta_description": (
            "Sign in to miscite to run citation checks, review manuscript integrity signals, "
            "and manage citation reports."
        ),
        "meta_keywords": (
            "citation checker login, manuscript citation reports, academic citation workflow"
        ),
        "robots": _DEFAULT_ROBOTS_INDEX,
        "twitter_card": "summary",
        "og_type": "website",
    },
    "/reports/access": {
        "meta_description": (
            "Open a shared miscite report with an access token to review citation flags, "
            "evidence summaries, and recommendation details."
        ),
        "meta_keywords": (
            "citation report access, manuscript citation report, research citation audit"
        ),
        "robots": _DEFAULT_ROBOTS_INDEX,
        "twitter_card": "summary",
        "og_type": "website",
    },
}


def _reference_source_names(reference_payload: Mapping[str, object] | None) -> list[str]:
    if not isinstance(reference_payload, Mapping):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for key in ("source", "venue", "publisher"):
        value = reference_payload.get(key)
        if not isinstance(value, str):
            continue
        name = " ".join(value.split()).strip()
        if not name:
            continue
        norm = name.casefold()
        if norm in seen:
            continue
        seen.add(norm)
        names.append(name)
    return names


def _reference_summary_text(reference_payload: Mapping[str, object] | None) -> str:
    if not isinstance(reference_payload, Mapping):
        return ""
    for key in ("apa", "apa_base", "title"):
        candidate = reference_payload.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return " ".join(candidate.split())[:320]
    return ""


def _reference_hover_text(reference_payload: Mapping[str, object] | None) -> str:
    summary = _reference_summary_text(reference_payload)
    sources = _reference_source_names(reference_payload)
    if summary and sources:
        return f"{summary} | Source: {' · '.join(sources)}"[:420]
    if summary:
        return summary
    if sources:
        return f"Source: {' · '.join(sources)}"[:420]
    return ""


def _reference_tooltip(reference_tooltips: Mapping[str, object] | None, rid: str) -> str:
    if not isinstance(reference_tooltips, Mapping):
        return ""
    payload = reference_tooltips.get(rid)
    if isinstance(payload, Mapping):
        text = _reference_hover_text(payload)
        if text:
            return text
    if isinstance(payload, str) and payload.strip():
        return " ".join(payload.split())[:320]
    return ""


def deep_cite_links(text: str | None, reference_tooltips: Mapping[str, object] | None = None) -> Markup:
    if not text:
        return Markup("")
    out: list[Markup] = []
    last = 0
    for m in _DEEP_CITE_RE.finditer(text):
        out.append(escape(text[last : m.start()]))
        num = m.group("num")
        rid = f"R{num}"
        tooltip = _reference_tooltip(reference_tooltips, rid)
        if tooltip:
            tip = escape(tooltip)
            out.append(
                Markup(
                    f'<a href="#da-ref-{rid}" class="miscite-mono" title="{tip}" aria-label="{tip}">[{rid}]</a>'
                )
            )
        else:
            out.append(Markup(f'<a href="#da-ref-{rid}" class="miscite-mono">[{rid}]</a>'))
        last = m.end()
    out.append(escape(text[last:]))
    return Markup("").join(out)


templates.env.filters["da_cite"] = deep_cite_links


def reference_sources(value: Mapping[str, object] | None) -> list[str]:
    return _reference_source_names(value)


templates.env.filters["reference_sources"] = reference_sources


def reference_hover_text(value: Mapping[str, object] | None) -> str:
    return _reference_hover_text(value)


templates.env.filters["reference_hover_text"] = reference_hover_text


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


def _is_local_origin(origin: str) -> bool:
    try:
        parsed = urlsplit(origin)
    except Exception:
        return True
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return True
    if host in _LOCAL_HOSTS:
        return True
    return host.endswith(".local")


def public_origin(request: Request) -> str:
    settings = request.app.state.settings

    configured_origin = str(getattr(settings, "public_origin", "") or "").strip().rstrip("/")
    if configured_origin and not _is_local_origin(configured_origin):
        return configured_origin

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
    path_defaults = _SEO_PATH_DEFAULTS.get(path, {})
    origin = public_origin(request)
    canonical_url = extra.get("canonical_url")
    if not canonical_url:
        canonical_url = f"{origin}{path}" if origin else path

    meta_description = extra.get("meta_description")
    if not meta_description:
        meta_description = path_defaults.get("meta_description") or "Audit-ready citation checks with evidence-first reports."

    meta_keywords = extra.get("meta_keywords")
    if not meta_keywords:
        meta_keywords = path_defaults.get("meta_keywords") or _DEFAULT_META_KEYWORDS

    robots = extra.get("robots")
    if not robots:
        robots = path_defaults.get("robots") or _DEFAULT_ROBOTS_NOINDEX

    og_type = extra.get("og_type")
    if not og_type:
        og_type = path_defaults.get("og_type", "website")

    twitter_card = extra.get("twitter_card")
    if not twitter_card:
        twitter_card = path_defaults.get("twitter_card", "summary")

    og_image_url = extra.get("og_image_url")
    if not og_image_url:
        og_image_url = f"{origin}/static/og-image.svg" if origin else "/static/og-image.svg"

    og_image_alt = extra.get("og_image_alt")
    if not og_image_alt:
        og_image_alt = "miscite citation-check report preview"

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
        "meta_keywords": meta_keywords,
        "robots": robots,
        "og_type": og_type,
        "twitter_card": twitter_card,
        "og_image_url": og_image_url,
        "og_image_alt": og_image_alt,
        **extra,
    }
