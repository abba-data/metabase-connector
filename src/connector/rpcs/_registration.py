from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from connector.registry import registry
from connector.rpcs import (
    arr_at_risk,
    channel_split,
    data_quality_signals,
    describe_catalog,
    execute_sql,
    license_query,
    mrr_trend,
    partner_revenue,
    read_audit,
    revenue_comparison,
    top_partners,
    upsell_opportunities,
)

if TYPE_CHECKING:
    from connector.settings import AppSettings

# Order is the order describe_catalog presents them in.
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
    execute_sql,
    read_audit,
]


def register_rpcs(app: FastAPI, settings: AppSettings) -> None:
    """Mount every RPC route once at boot. Per CLAUDE.md the registry is the
    only place where 'what RPCs exist' lives; no parallel hand-maintained list.

    Card IDs come from `settings` (Pydantic-loaded), not module-level env reads.
    """
    for mod in _RPC_MODULES:
        descriptor = mod.DESCRIPTOR
        card_attr = f"card_id_{descriptor.name}"
        card_id = getattr(settings, card_attr, None)
        if card_id is not None:
            # Mutate the module-level descriptor so handlers that reference
            # `mod.DESCRIPTOR` see the wired card id. Pydantic v2 models are
            # mutable by default; this happens once at boot.
            descriptor.metabase_card_id = card_id
        registry.register(descriptor)
        app.include_router(mod.router)
