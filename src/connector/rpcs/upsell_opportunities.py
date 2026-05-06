from __future__ import annotations

from decimal import Decimal
from enum import Enum

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from connector.models import Response, Scope
from connector.registry import RpcDescriptor
from connector.rpcs._helpers import execute_card_rows, wrap
from connector.security.scopes import require_scope

router = APIRouter()


class PricingStructure(str, Enum):
    CLOUD_MARGINAL_BAND = "cloud_marginal_band"
    DC_FLAT_ANNUAL = "dc_flat_annual"
    SERVER_PURCHASE_RENEWAL = "server_purchase_renewal"


class UpsellOpportunitiesInput(BaseModel):
    horizon_days: int = Field(default=60, ge=1, le=730)
    min_seat_delta: int = Field(default=1, ge=1)


class UpsellRow(BaseModel):
    license_id: str
    partner: str | None = None
    app: str
    current_seats: int
    projected_seats: int
    current_arr: Decimal
    projected_arr: Decimal
    delta_arr: Decimal
    pricing_structure: PricingStructure | None = None


class UpsellOpportunitiesOutput(BaseModel):
    rows: list[UpsellRow]


DESCRIPTOR = RpcDescriptor(
    name="upsell_opportunities",
    version="1.0.0",
    description="Tier-grown licenses approaching renewal with projected re-priced ARR. Projection arithmetic lives in saved-question SQL.",
    input_model=UpsellOpportunitiesInput,
    output_model=UpsellOpportunitiesOutput,
    metabase_card_id=None,
    required_scope=Scope.GENERAL,
)


def _params(inp: UpsellOpportunitiesInput) -> list[dict]:
    return [
        {
            "type": "number/=",
            "target": ["variable", ["template-tag", "horizon_days"]],
            "value": inp.horizon_days,
        },
        {
            "type": "number/=",
            "target": ["variable", ["template-tag", "min_seat_delta"]],
            "value": inp.min_seat_delta,
        },
    ]


def _coerce_pricing(value: object) -> PricingStructure | None:
    if value is None:
        return None
    try:
        return PricingStructure(str(value))
    except ValueError:
        return None


@router.post(
    "/rpc/upsell_opportunities",
    response_model=Response[UpsellOpportunitiesOutput],
    tags=["catalog"],
)
async def upsell_opportunities(
    request: Request,
    body: UpsellOpportunitiesInput,
    consumer=Depends(require_scope(Scope.GENERAL)),
) -> Response[UpsellOpportunitiesOutput]:
    rows = await execute_card_rows(request, DESCRIPTOR, parameters=_params(body))
    out_rows = [
        UpsellRow(
            license_id=str(r.get("license_id") or r.get("id") or ""),
            partner=r.get("partner"),
            app=str(r.get("app") or ""),
            current_seats=int(r.get("current_seats") or 0),
            projected_seats=int(r.get("projected_seats") or 0),
            current_arr=Decimal(str(r.get("current_arr") or 0)),
            projected_arr=Decimal(str(r.get("projected_arr") or 0)),
            delta_arr=Decimal(str(r.get("delta_arr") or 0)),
            pricing_structure=_coerce_pricing(r.get("pricing_structure")),
        )
        for r in rows
    ]
    return wrap(request, DESCRIPTOR, UpsellOpportunitiesOutput(rows=out_rows))
