from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates

from server.miscite.security import get_csrf_cookie

templates = Jinja2Templates(directory="server/miscite/templates")


def template_context(request: Request, **extra):
    return {
        "request": request,
        "current_user": getattr(request.state, "user", None),
        "csrf_token": get_csrf_cookie(request) or "",
        **extra,
    }

