from __future__ import annotations

import argparse
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from server.miscite.cli import add_runtime_args, apply_runtime_overrides
from server.miscite.config import Settings
from server.miscite.db import init_db
from server.miscite.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from server.miscite.routes import auth, billing, dashboard, health


def create_app() -> FastAPI:
    load_dotenv()
    settings = Settings.from_env()

    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    init_db(settings)

    app = FastAPI(title="miscite", version="0.1.0")
    app.state.settings = settings

    app.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=settings.max_body_mb * 1024 * 1024,
        include_paths=("/upload", "/register", "/login", "/reports/access", "/billing", "/jobs"),
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(billing.router)

    app.mount("/static", StaticFiles(directory="server/miscite/static"), name="static")
    return app


if __name__ != "__main__":
    app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run miscite web service.")
    add_runtime_args(parser)
    args = parser.parse_args()

    load_dotenv()
    apply_runtime_overrides(args)
    reload = os.getenv("MISCITE_RELOAD", "").strip().lower() in {"1", "true", "yes", "y", "on"}
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=reload)


if __name__ == "__main__":
    main()
