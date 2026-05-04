from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator

from connector.models import Response, Scope
from connector.registry import RpcDescriptor
from connector.rpc_config import CARD_ID_TOP_PARTNERS
from connector.rpcs._helpers import execute_card_rows, wrap
from connector.security.scopes import require_scope

router = APIRouter()


class TopPartnersInput(BaseModel):
    start_date: date
    end_date: date
    limit: int = Field(default=10, ge=1, le=100)
    consolidate: bool = True

    @model_validator(mode="after")
    def _check_dates(self) -> "TopPartnersInput":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class TopPartnerRow(BaseModel):
    rank: int
    partner: str
    canonical_parent: str | None = None
    net_revenue: Decimal


class TopPartnersOutput(BaseModel):
    rows: list[TopPartnerRow]


DESCRIPTOR = RpcDescriptor(
    name="top_partners",
    version="1.0.0",
    description="Ranked partner list by net revenue over the date window.",
    input_model=TopPartnersInput,
    output_model=TopPartnersOutput,
    metabase_card_id=CARD_ID_TOP_PARTNERS,
    required_scope=Scope.GENERAL,
)


def _params(inp: TopPartnersInput) -> list[dict]:
    return [
        {"type": "date/single", "target": ["variable", ["template-tag", "start_date"]], "value": inp.start_date.isoformat()},
        {"type": "date/single", "target": ["variable", ["template-tag", "end_date"]], "value": inp.end_date.isoformat()},
        {"type": "number/=", "target": ["variable", ["template-tag", "limit"]], "value": inp.limit},
        {"type": "category", "target": ["variable", ["template-tag", "consolidate"]], "value": inp.consolidate},
    ]


@router.post(
    "/rpc/top_partners",
    response_model=Response[TopPartnersOutput],
    tags=["catalog"],
)
async def top_partners(
    request: Request,
    body: TopPartnersInput,
    consumer=Depends(require_scope(Scope.GENERAL)),
) -> Response[TopPartnersOutput]:
    rows = await execute_card_rows(request, DESCRIPTOR, parameters=_params(body))
    out_rows: list[TopPartnerRow] = []
    for i, r in enumerate(rows, start=1):
        out_rows.append(
            TopPartnerRow(
                rank=int(r.get("rank") or i),
                partner=str(r.get("partner") or r.get("partner_name") or ""),
                canonical_parent=r.get("canonical_parent"),
                net_revenue=Decimal(str(r.get("net_revenue", 0))),
            )
        )
    return wrap(request, DESCRIPTOR, TopPartnersOutput(rows=out_rows))
