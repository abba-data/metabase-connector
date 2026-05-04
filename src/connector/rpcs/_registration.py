from __future__ import annotations

from fastapi import FastAPI

from connector.registry import registry
from connector.rpcs import (
    arr_at_risk,
    channel_split,
    data_quality_signals,
    describe_catalog,
    license_query,
    mrr_trend,
    partner_revenue,
    revenue_comparison,
    top_partners,
    upsell_opportunities,
)

# Order matters only for describe_catalog presenting a stable list.
_RPC_MODULES = [
    describe_catalog,
    partner_revenue,
    channel_split,
    top_partners,
    mrr_trend,
    arr_at_risk,
    upsell_opportunities,
    revenue_comparison,
    data_quality_signals,
    license_query,
]


def register_rpcs(app: FastAPI) -> None:
    """Single boot-time mount path. No FastAPI route may exist outside this function.

    Each RPC module exposes:
      - DESCRIPTOR: RpcDescriptor
      - router: APIRouter with one POST /rpc/<name>
    """
    for mod in _RPC_MODULES:
        registry.register(mod.DESCRIPTOR)
        app.include_router(mod.router)
