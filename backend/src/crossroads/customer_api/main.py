"""Customer API.

This module must never import `crossroads.internal_api` (FR-023, FR-026): the two services share
only the engine, db and adapters packages.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..config import Config, load_settings
from ..db.repo import make_pool
from .routes import router
from .store import CustomerStore, DbStore


def create_app(store: CustomerStore | None = None, cfg: Config | None = None) -> FastAPI:
    """The app. Without a `store` it reads the database named by DATABASE_URL; tests pass one in."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = None
        if store is None:
            pool = make_pool(load_settings().database_url)
            pool.open()
            app.state.store = DbStore(pool)
        yield
        if pool is not None:
            pool.close()

    app = FastAPI(
        title="Crossroads customer API",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        lifespan=lifespan,
    )
    app.state.cfg = cfg or Config()
    if store is not None:
        app.state.store = store
    app.include_router(router)

    @app.exception_handler(psycopg.Error)
    async def database_unavailable(request: Request, exc: psycopg.Error) -> JSONResponse:
        # A readable message, never a stack trace (principle VI).
        return JSONResponse(
            status_code=503,
            content={"detail": "Customer data is temporarily unavailable. Please try again in a moment."},
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
