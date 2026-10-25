"""Customer routes. Every route answers for one selected customer and never returns anyone else's
data or any cross-customer figure (FR-024)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..adapters.dealers import DealersClient
from ..config import Config
from ..engine.next_steps import NEXT_STEP_LABELS, next_step_of
from ..engine.schemas import LEASE_PATHS, LOAN_PATHS, PATH_LABELS
from ..explain.service import ExplainService
from .dealers_service import nearby_dealers
from .overview import build_overview, build_spending
from .paths_service import (
    InvalidInput,
    apply_request,
    build_explanation,
    build_paths_response,
    confirmation_text,
    default_inputs,
)
from .schemas import (
    CustomerListItem,
    DealerOut,
    DealersResponse,
    ExplanationOut,
    NextStepRequest,
    NextStepResponse,
    OverviewResponse,
    PathsRequest,
    PathsResponse,
    SpendingResponse,
)
from .store import CustomerRecord, CustomerStore

router = APIRouter(prefix="/api")


def get_store(request: Request) -> CustomerStore:
    return request.app.state.store


def get_cfg(request: Request) -> Config:
    return request.app.state.cfg


def get_explain(request: Request) -> ExplainService:
    return request.app.state.explain


def get_dealers(request: Request) -> DealersClient | None:
    return request.app.state.dealers


def _record(store: CustomerStore, customer_id: str) -> CustomerRecord:
    rec = store.get_record(customer_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="We couldn't find that customer.")
    return rec


@router.get("/customers", response_model=list[CustomerListItem])
def list_customers(store: CustomerStore = Depends(get_store)):
    return [CustomerListItem(**vars(c)) for c in store.list_customers()]


@router.get("/customers/{customer_id}/overview", response_model=OverviewResponse)
def overview(customer_id: str, store: CustomerStore = Depends(get_store), cfg: Config = Depends(get_cfg)):
    rec = _record(store, customer_id)
    return build_overview(rec, store.monthly_miles(customer_id), cfg)


@router.get("/customers/{customer_id}/spending", response_model=SpendingResponse)
def spending(customer_id: str, store: CustomerStore = Depends(get_store)):
    _record(store, customer_id)
    return build_spending(store.monthly_spend(customer_id))


def _scenario_for(rec: CustomerRecord, body: PathsRequest | None, cfg: Config):
    base = default_inputs(rec, cfg)
    try:
        return base, apply_request(base, body or PathsRequest())
    except InvalidInput as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/customers/{customer_id}/paths", response_model=PathsResponse)
def paths(
    customer_id: str,
    body: PathsRequest | None = None,
    store: CustomerStore = Depends(get_store),
    cfg: Config = Depends(get_cfg),
    explain: ExplainService = Depends(get_explain),
):
    """Every path for this customer, the recommendation, and what would flip it. Send no body (or
    leave inputs out) to get the customer's own defaults, which come back in `inputs_used`."""
    base, inp = _scenario_for(_record(store, customer_id), body, cfg)
    return build_paths_response(inp, base.scenario.monthly_budget, cfg, explain)


@router.get("/customers/{customer_id}/dealers", response_model=DealersResponse)
def dealers(
    customer_id: str,
    store: CustomerStore = Depends(get_store),
    client: DealersClient | None = Depends(get_dealers),
):
    """The three Toyota dealers nearest this customer, nearest first. An empty list is a valid answer."""
    found = nearby_dealers(store, client, _record(store, customer_id))
    return DealersResponse(
        dealers=[
            DealerOut(name=d.name, address=d.address, hours=d.hours, rating=d.rating, distance_miles=d.distance_miles)
            for d in found
        ]
    )


@router.post("/customers/{customer_id}/next-step", response_model=NextStepResponse)
def next_step(customer_id: str, body: NextStepRequest, store: CustomerStore = Depends(get_store)):
    """Confirm the customer's chosen next step, or a request to talk to a specialist. Stateless: it
    starts no transaction and stores nothing."""
    rec = _record(store, customer_id)
    allowed = LEASE_PATHS if rec.contract.type == "lease" else LOAN_PATHS
    if body.path not in allowed:
        raise HTTPException(status_code=422, detail="That is not one of your options.")
    step = next_step_of(body.path)
    return NextStepResponse(
        path_label=PATH_LABELS[body.path],
        confirmation=confirmation_text(body.path, body.kind),
        step_type=step,
        step_label=NEXT_STEP_LABELS[step],
    )


@router.post("/customers/{customer_id}/explanation", response_model=ExplanationOut)
def explanation(
    customer_id: str,
    body: PathsRequest | None = None,
    store: CustomerStore = Depends(get_store),
    cfg: Config = Depends(get_cfg),
    explain: ExplainService = Depends(get_explain),
):
    """The model's explanation of the recommendation. It is only ever returned if it passed the
    number check; otherwise this returns the checked template."""
    _, inp = _scenario_for(_record(store, customer_id), body, cfg)
    return build_explanation(inp, cfg, explain)
