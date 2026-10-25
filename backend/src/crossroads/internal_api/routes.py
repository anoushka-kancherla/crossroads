"""Internal routes. Sign-in is the only one open; every other route needs a valid staff session, checked
here in the API (FR-025)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..config import Config
from ..customer_api.store import CustomerStore
from ..explain.service import ExplainService
from .auth import (
    COOKIE,
    COOKIE_PATH,
    SESSION_SECONDS,
    AuthState,
    check_credentials,
    client_ip,
    make_token,
    require_staff,
)
from .live_service import build_live, etag_of
from .portfolio_service import build_portfolio, refresh_snapshots
from .schemas import FairnessResponse, LiveResponse, LoginRequest, PortfolioResponse, SessionOut, fairness_response
from .snapshots import SnapshotStore

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/internal")


@router.post("/login", status_code=204)
def login(body: LoginRequest, request: Request, response: Response):
    auth: AuthState = request.app.state.auth
    if not auth.configured:
        raise HTTPException(status_code=503, detail="Staff sign-in isn't set up yet.")
    ip, now = client_ip(request), auth.clock()
    # A locked address is refused before the password is looked at, so the answer says nothing about it.
    wait = auth.limiter.retry_after(ip, now)
    if wait:
        raise HTTPException(
            status_code=429, detail="Too many attempts. Please try again later.", headers={"Retry-After": str(wait)}
        )
    # One message for a wrong username and a wrong password, so neither can be told apart.
    if not check_credentials(auth.user, auth.password_hash, body.username, body.password):
        auth.limiter.record_failure(ip, now)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    auth.limiter.reset(ip)
    response.set_cookie(
        COOKIE,
        make_token(auth.user, auth.secret, auth.clock()),
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        secure=auth.secure,
        path=COOKIE_PATH,
    )


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, staff: dict = Depends(require_staff)):
    request.app.state.auth.revoke(staff["jti"], int(staff["exp"]))
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, samesite="strict")


@router.get("/session", response_model=SessionOut)
def session(staff: dict = Depends(require_staff)):
    return SessionOut(user=staff["sub"])


@router.get("/portfolio", response_model=PortfolioResponse)
def portfolio(request: Request, _: dict = Depends(require_staff)):
    snapshots: SnapshotStore = request.app.state.snapshots
    return build_portfolio(snapshots.load())


@router.post("/portfolio/refresh", response_model=PortfolioResponse)
def refresh(request: Request, _: dict = Depends(require_staff)):
    """Recompute every customer's recommendation (and its explanation check) and return the new portfolio."""
    state = request.app.state
    store: CustomerStore = state.store
    cfg: Config = state.cfg
    explain: ExplainService = state.explain
    portfolio = build_portfolio(refresh_snapshots(store, state.snapshots, cfg, explain))
    try:  # the fairness figures are recomputed too, but a failure there never touches the portfolio
        state.fairness.recompute()
    except Exception:
        log.exception("The fairness report could not be recomputed")
    return portfolio


@router.get("/live", response_model=LiveResponse)
def live(request: Request, response: Response, _: dict = Depends(require_staff)):
    """The live acceptance figures. Sends an ETag, and 304 when nothing has changed since the caller's copy."""
    try:
        figures = build_live(request.app.state.store)
    except Exception:
        log.exception("The live figures could not be read")
        raise HTTPException(status_code=503, detail="We can't load the live figures right now.") from None
    tag = etag_of(figures)
    headers = {"ETag": tag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return figures


@router.get("/fairness", response_model=FairnessResponse)
def fairness(request: Request, _: dict = Depends(require_staff)):
    """The fairness check on the separate synthetic population: band-level figures only, read-only."""
    try:
        return fairness_response(request.app.state.fairness.get())
    except Exception:
        log.exception("The fairness report could not be computed")
        raise HTTPException(status_code=503, detail="We couldn't work out the fairness figures right now.") from None


@router.get("/openapi.json", include_in_schema=False)
def openapi(request: Request, _: dict = Depends(require_staff)):
    """The API description is behind the same sign-in as the data."""
    return request.app.openapi()
