from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from connector.models import Response, Scope
from connector.registry import RpcDescriptor
from connector.rpc_config import CARD_ID_MRR_TREND
from connector.rpcs._helpers import execute_card_rows, wrap
from connector.security.scopes import require_scope

router = APIRouter()


class MrrTrendInput(BaseModel):
    months_back: int = Field(default=24, ge=1, le=120)
    partner_subtype: str | None = None


class MrrPoint(BaseModel):
    month: date
    mrr: Decimal
    by_customer_type: dict[str, Decimal] = Field(default_factory=dict)
    by_partner_type: dict[str, Decimal] = Field(default_factory=dict)


class MrrTrendOutput(BaseModel):
    series: list[MrrPoint]


DESCRIPTOR = RpcDescriptor(
    name="mrr_trend",
    version="1.0.0",
    description="Monthly MRR series with customer-type and partner-type breakdowns. Backed by Metabase #159 methodology.",
    input_model=MrrTrendInput,
    output_model=MrrTrendOutput,
    metabase_card_id=CARD_ID_MRR_TREND,
    required_scope=Scope.GENERAL,
)


def _params(inp: MrrTrendInput) -> list[dict]:
    params: list[dict] = [
        {"type": "number/=", "target": ["variable", ["template-tag", "months_back"]], "value": inp.months_back},
    ]
    if inp.partner_subtype is not None:
        params.append(
            {"type": "category", "target": ["variable", ["template-tag", "partner_subtype"]], "value": inp.partner_subtype}
        )
    return params


def _reshape(rows: list[dict[str, Any]]) -> list[MrrPoint]:
    """Group flat row-per-month-per-segment shape into one MrrPoint per month."""
    by_month: dict[str, MrrPoint] = {}
    for r in rows:
        month_val = r.get("mrr_month") or r.get("month")
        if month_val is None:
            continue
        month_key = str(month_val)[:10]
        contribution = Decimal(str(r.get("mrr_contribution") or r.get("mrr") or 0))
        point = by_month.get(month_key)
        if point is None:
            point = MrrPoint(month=date.fromisoformat(month_key), mrr=Decimal(0))
            by_month[month_key] = point
        point.mrr = point.mrr + contribution
        ct = r.get("customer_type")
        if ct is not None:
            point.by_customer_type[str(ct)] = point.by_customer_type.get(str(ct), Decimal(0)) + contribution
        pt = r.get("partner_type")
        if pt is not None:
            point.by_partner_type[str(pt)] = point.by_partner_type.get(str(pt), Decimal(0)) + contribution
    return [by_month[k] for k in sorted(by_month.keys())]


@router.post(
    "/rpc/mrr_trend",
    response_model=Response[MrrTrendOutput],
    tags=["catalog"],
)
async def mrr_trend(
    request: Request,
    body: MrrTrendInput,
    consumer=Depends(require_scope(Scope.GENERAL)),
) -> Response[MrrTrendOutput]:
    rows = await execute_card_rows(request, DESCRIPTOR, parameters=_params(body))
    return wrap(request, DESCRIPTOR, MrrTrendOutput(series=_reshape(rows)))
