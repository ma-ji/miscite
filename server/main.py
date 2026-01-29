from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from server.miscite.config import Settings
from server.miscite.db import init_db
from server.miscite.routes import auth, billing, dashboard, health


def create_app() -> FastAPI:
    load_dotenv()
    settings = Settings.from_env()

    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    init_db(settings)

    app = FastAPI(title="miscite", version="0.1.0")
    app.state.settings = settings

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(billing.router)

    app.mount("/static", StaticFiles(directory="server/miscite/static"), name="static")
    return app


app = create_app()


def main() -> None:
    load_dotenv()
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
