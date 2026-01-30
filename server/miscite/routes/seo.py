from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from server.miscite.web import public_origin

router = APIRouter()


@router.get("/robots.txt")
def robots_txt(request: Request):
    origin = public_origin(request)
    sitemap_url = f"{origin}/sitemap.xml" if origin else "/sitemap.xml"
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /dashboard",
            "Disallow: /jobs",
            "Disallow: /reports",
            "Disallow: /login",
            "Disallow: /billing",
            "Disallow: /api/",
            "Disallow: /upload",
            "Disallow: /logout",
            f"Sitemap: {sitemap_url}",
            "",
        ]
    )
    return PlainTextResponse(body, media_type="text/plain; charset=utf-8")


@router.get("/sitemap.xml")
def sitemap_xml(request: Request):
    origin = public_origin(request)
    root_url = f"{origin}/" if origin else "/"
    lastmod = dt.datetime.now(dt.UTC).date().isoformat()
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{root_url}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""
    return Response(body, media_type="application/xml; charset=utf-8")


@router.get("/favicon.ico")
def favicon_ico():
    return RedirectResponse("/static/favicon.svg", status_code=307)

