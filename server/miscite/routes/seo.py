from __future__ import annotations

import datetime as dt
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from server.miscite.web import SEO_SITEMAP_ENTRIES, public_origin

router = APIRouter()


@router.get("/robots.txt")
def robots_txt(request: Request):
    origin = public_origin(request)
    sitemap_url = f"{origin}/sitemap.xml" if origin else "/sitemap.xml"
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Allow: /login",
            "Allow: /reports/access",
            "Disallow: /dashboard",
            "Disallow: /jobs/",
            "Disallow: /reports/",
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
    lastmod = dt.datetime.now(dt.UTC).date().isoformat()
    urls: list[str] = []
    for entry in SEO_SITEMAP_ENTRIES:
        path = entry.get("path", "/")
        changefreq = entry.get("changefreq", "monthly")
        priority = entry.get("priority", "0.5")
        loc = f"{origin}{path}" if origin else path
        urls.append(
            "\n".join(
                [
                    "  <url>",
                    f"    <loc>{xml_escape(loc)}</loc>",
                    f"    <lastmod>{lastmod}</lastmod>",
                    f"    <changefreq>{xml_escape(changefreq)}</changefreq>",
                    f"    <priority>{xml_escape(priority)}</priority>",
                    "  </url>",
                ]
            )
        )
    body = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
""".format(urls="\n".join(urls))
    return Response(body, media_type="application/xml; charset=utf-8")


@router.get("/favicon.ico")
def favicon_ico():
    return RedirectResponse("/static/favicon.svg", status_code=307)
