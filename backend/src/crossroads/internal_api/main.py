"""Internal API: the staff dashboard's data. Every route but sign-in needs a staff session.

Nothing here is reachable from the customer app: it is a separate process on its own network (FR-023,
FR-026). It reuses the customer data store for reading customers, but exposes no customer route.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..adapters.llm import LLMClient, make_llm
from ..config import Config, Settings, load_settings
from ..customer_api.store import CustomerStore, DbStore
from ..db.repo import make_pool
from ..explain.service import ExplainService
from .auth import AuthState
from .routes import router
from .snapshots import DbSnapshots, SnapshotStore


def create_app(
    settings: Settings | None = None,
    store: CustomerStore | None = None,
    snapshots: SnapshotStore | None = None,
    cfg: Config | None = None,
    llm: LLMClient | None = None,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    """The app. Without a `store` it reads the database named by DATABASE_URL; tests pass in a store,
    snapshots, settings (with a throwaway hash) and a clock."""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = None
        if store is None:
            pool = make_pool(settings.database_url)
            pool.open()
            app.state.store = DbStore(pool)
            app.state.snapshots = DbSnapshots(pool)
        yield
        if pool is not None:
            pool.close()

    # No public schema or docs: the API description is itself behind the sign-in (see routes.py).
    app = FastAPI(title="Crossroads internal API", openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.cfg = cfg or Config()
    app.state.auth = AuthState(
        user=settings.staff_user,
        password_hash=settings.staff_password_hash,
        secret=settings.session_secret,
        secure=settings.cookie_secure,
        clock=clock,
    )
    if store is not None:
        app.state.store = store
        app.state.snapshots = snapshots
    if store is None and llm is None:
        llm = make_llm(settings)
    app.state.explain = ExplainService(llm)
    app.include_router(router)

    @app.exception_handler(psycopg.Error)
    async def database_unavailable(request: Request, exc: psycopg.Error) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "Data is temporarily unavailable. Please try again."})

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "Please check what you entered."})

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}  # no data, and no sign-in needed

    return app


app = create_app()
