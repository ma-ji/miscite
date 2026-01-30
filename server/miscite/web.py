from __future__ import annotations

import re

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from server.miscite.security import get_csrf_cookie

templates = Jinja2Templates(directory="server/miscite/templates")


_DEEP_CITE_RE = re.compile(r"\[R(?P<num>\d{1,4})\]")


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


def template_context(request: Request, **extra):
    return {
        "request": request,
        "current_user": getattr(request.state, "user", None),
        "csrf_token": get_csrf_cookie(request) or "",
        "record_estimate": "250M+",
        **extra,
    }
