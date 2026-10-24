"""Customer routes. Every route answers for one selected customer and never returns anyone else's
data or any cross-customer figure (FR-024)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..config import Config
from .overview import build_overview, build_spending
from .schemas import CustomerListItem, OverviewResponse, SpendingResponse
from .store import CustomerRecord, CustomerStore

router = APIRouter(prefix="/api")


def get_store(request: Request) -> CustomerStore:
    return request.app.state.store


def get_cfg(request: Request) -> Config:
    return request.app.state.cfg


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
