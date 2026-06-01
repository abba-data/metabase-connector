from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from connector.models import Response, Scope
from connector.registry import RpcDescriptor
from connector.rpcs._helpers import (
    execute_card_rows,
    execute_dataset_rows,
    get_settings_from_request,
    should_use_new_sql,
    wrap,
)
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
    description=(
        "Monthly MRR series with customer-type and partner-type breakdowns. "
        "Backed by Metabase #159 methodology (card path) or dbt_marts.mart_mrr_monthly_by_channel (Q159 v2.2)."
    ),
    input_model=MrrTrendInput,
    output_model=MrrTrendOutput,
    metabase_card_id=None,
    sql_file="mrr_trend.sql",
    required_scope=Scope.GENERAL,
)


def _card_params(inp: MrrTrendInput) -> list[dict]:
    """Parameter payload for the legacy card path."""
    params: list[dict] = [
        {
            "type": "number/=",
            "target": ["variable", ["template-tag", "months_back"]],
            "value": inp.months_back,
        },
    ]
    if inp.partner_subtype is not None:
        params.append(
            {
                "type": "category",
                "target": ["variable", ["template-tag", "partner_subtype"]],
                "value": inp.partner_subtype,
            }
        )
    return params


# Back-compat re-export for tests / external callers.
_params = _card_params


def _dataset_params(inp: MrrTrendInput) -> list[dict]:
    """Parameter payload for the native-SQL dataset path. Same shape as the
    card path here — the differences (booleans/lists) only show up in other RPCs."""
    return _card_params(inp)


def _dataset_template_tags(inp: MrrTrendInput) -> dict[str, dict[str, Any]]:
    _ = inp
    return {
        "months_back": {
            "id": "months_back",
            "name": "months_back",
            "display-name": "Months back",
            "type": "number",
            "required": True,
        },
        "partner_subtype": {
            "id": "partner_subtype",
            "name": "partner_subtype",
            "display-name": "Partner subtype",
            "type": "text",
            "required": False,
        },
    }


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
    settings = get_settings_from_request(request)
    use_new = should_use_new_sql(DESCRIPTOR, settings)
    if use_new:
        rows = await execute_dataset_rows(
            request,
            DESCRIPTOR,
            template_tags=_dataset_template_tags(body),
            parameters=_dataset_params(body),
        )
    else:
        rows = await execute_card_rows(request, DESCRIPTOR, parameters=_card_params(body))
    return wrap(request, DESCRIPTOR, MrrTrendOutput(series=_reshape(rows)), via_sql=use_new)
