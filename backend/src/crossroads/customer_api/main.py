"""Customer API.

This module must never import `crossroads.internal_api` (FR-023, FR-026): the two services share
only the engine, db and adapters packages.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..adapters.llm import LLMClient, make_llm
from ..config import Config, load_settings
from ..db.repo import make_pool
from ..explain.service import ExplainService
from .routes import router
from .store import CustomerStore, DbStore

_FIELD_LABELS = {
    "miles_per_year": "Miles per year",
    "monthly_budget": "Monthly budget",
    "years_to_keep": "Years you plan to keep a car",
    "financing_rate": "Financing rate",
}


def create_app(
    store: CustomerStore | None = None, cfg: Config | None = None, llm: LLMClient | None = None
) -> FastAPI:
    """The app. Without a `store` it reads the database named by DATABASE_URL and takes the model
    from the environment (none without a key); tests pass a store, and a fake model if they want one."""

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
    if llm is None and store is None:
        llm = make_llm(load_settings())
    app.state.explain = ExplainService(llm)
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
        # One readable sentence for the screen, plus the fields for anything that wants them.
        errors = [
            {"field": str(e["loc"][-1]), "message": e["msg"]} for e in exc.errors() if e.get("loc")
        ]
        parts = [f"{_FIELD_LABELS.get(e['field'], e['field'])}: {e['message']}" for e in errors]
        return JSONResponse(
            status_code=422,
            content={"detail": "; ".join(parts) or "Please check your inputs.", "errors": errors},
        )

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
