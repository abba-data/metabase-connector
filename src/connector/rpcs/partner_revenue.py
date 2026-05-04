from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator

from connector.models import Response, Scope
from connector.registry import RpcDescriptor
from connector.rpc_config import CARD_ID_PARTNER_REVENUE
from connector.rpcs._helpers import execute_card_rows, wrap
from connector.security.scopes import require_scope

router = APIRouter()


LicenseTypeLiteral = Literal["COMMERCIAL", "ACADEMIC"]


class PartnerRevenueInput(BaseModel):
    start_date: date
    end_date: date
    consolidate: bool = True
    license_types: list[LicenseTypeLiteral] = Field(default_factory=lambda: ["COMMERCIAL", "ACADEMIC"])

    @model_validator(mode="after")
    def _check_dates(self) -> "PartnerRevenueInput":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class PartnerRevenueRow(BaseModel):
    partner: str | None = None
    canonical_parent: str | None = None
    net_revenue: Decimal
    line_count: int | None = None
    distinct_license_count: int | None = None


class PartnerRevenueOutput(BaseModel):
    rows: list[PartnerRevenueRow]


DESCRIPTOR = RpcDescriptor(
    name="partner_revenue",
    version="1.0.0",
    description="Net revenue per partner over the date window. Applies canonical partner scope, license-type filter, and vendorAmount sign convention.",
    input_model=PartnerRevenueInput,
    output_model=PartnerRevenueOutput,
    metabase_card_id=CARD_ID_PARTNER_REVENUE,
    required_scope=Scope.GENERAL,
)


def _params(inp: PartnerRevenueInput) -> list[dict]:
    return [
        {"type": "date/single", "target": ["variable", ["template-tag", "start_date"]], "value": inp.start_date.isoformat()},
        {"type": "date/single", "target": ["variable", ["template-tag", "end_date"]], "value": inp.end_date.isoformat()},
        {"type": "category", "target": ["variable", ["template-tag", "consolidate"]], "value": inp.consolidate},
        {"type": "category", "target": ["variable", ["template-tag", "license_types"]], "value": list(inp.license_types)},
    ]


@router.post(
    "/rpc/partner_revenue",
    response_model=Response[PartnerRevenueOutput],
    tags=["catalog"],
)
async def partner_revenue(
    request: Request,
    body: PartnerRevenueInput,
    consumer=Depends(require_scope(Scope.GENERAL)),
) -> Response[PartnerRevenueOutput]:
    rows = await execute_card_rows(request, DESCRIPTOR, parameters=_params(body))
    out = PartnerRevenueOutput(rows=[PartnerRevenueRow.model_validate(r) for r in rows])
    return wrap(request, DESCRIPTOR, out)
