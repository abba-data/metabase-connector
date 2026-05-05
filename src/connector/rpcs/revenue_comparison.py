from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from enum import Enum

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, model_validator

from connector.models import Response, Scope
from connector.registry import RpcDescriptor
from connector.rpc_config import CARD_ID_REVENUE_COMPARISON
from connector.rpcs._helpers import execute_card_rows, wrap
from connector.security.scopes import require_scope

router = APIRouter()


class Dimension(str, Enum):
    CHANNEL = "channel"
    SALE_TYPE = "sale_type"
    PARTNER = "partner"


class Period(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _check(self) -> Period:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


_QUARTER_RE = re.compile(r"^Q([1-4])\s+(\d{4})$", re.IGNORECASE)


def parse_period(text: str) -> Period:
    """Parse canonical period strings to a Period.

    Supports: 'Q1 2025', 'Q4 2026'. Other tokens raise ValueError so the
    caller surfaces a CRT-01C VALIDATION_ERROR.
    """
    s = text.strip()
    m = _QUARTER_RE.match(s)
    if m:
        q = int(m.group(1))
        y = int(m.group(2))
        start_month = (q - 1) * 3 + 1
        start = date(y, start_month, 1)
        end_month = start_month + 2
        end_day = date(y, end_month + 1, 1) if end_month < 12 else date(y + 1, 1, 1)
        from datetime import timedelta

        end = end_day - timedelta(days=1)
        return Period(start_date=start, end_date=end)
    raise ValueError(f"Unrecognized period string: {text!r}")


class RevenueComparisonInput(BaseModel):
    period_a: Period | str
    period_b: Period | str
    dimension: Dimension = Dimension.CHANNEL

    @model_validator(mode="after")
    def _coerce(self) -> RevenueComparisonInput:
        if isinstance(self.period_a, str):
            object.__setattr__(self, "period_a", parse_period(self.period_a))
        if isinstance(self.period_b, str):
            object.__setattr__(self, "period_b", parse_period(self.period_b))
        return self


class DimensionTotal(BaseModel):
    key: str
    revenue: Decimal


class PeriodSummary(BaseModel):
    total: Decimal
    by_dimension: list[DimensionTotal]


class DimensionDelta(BaseModel):
    key: str
    period_a: Decimal
    period_b: Decimal
    delta: Decimal


class RevenueComparisonOutput(BaseModel):
    period_a: PeriodSummary
    period_b: PeriodSummary
    deltas: list[DimensionDelta]


DESCRIPTOR = RpcDescriptor(
    name="revenue_comparison",
    version="1.0.0",
    description="Period-over-period net-revenue comparison split by channel / sale_type / partner.",
    input_model=RevenueComparisonInput,
    output_model=RevenueComparisonOutput,
    metabase_card_id=CARD_ID_REVENUE_COMPARISON,
    required_scope=Scope.GENERAL,
)


def _params(inp: RevenueComparisonInput) -> list[dict]:
    a = inp.period_a if isinstance(inp.period_a, Period) else parse_period(str(inp.period_a))
    b = inp.period_b if isinstance(inp.period_b, Period) else parse_period(str(inp.period_b))
    return [
        {
            "type": "date/single",
            "target": ["variable", ["template-tag", "period_a_start"]],
            "value": a.start_date.isoformat(),
        },
        {
            "type": "date/single",
            "target": ["variable", ["template-tag", "period_a_end"]],
            "value": a.end_date.isoformat(),
        },
        {
            "type": "date/single",
            "target": ["variable", ["template-tag", "period_b_start"]],
            "value": b.start_date.isoformat(),
        },
        {
            "type": "date/single",
            "target": ["variable", ["template-tag", "period_b_end"]],
            "value": b.end_date.isoformat(),
        },
        {
            "type": "category",
            "target": ["variable", ["template-tag", "dimension"]],
            "value": inp.dimension.value,
        },
    ]


def _reshape(rows: list[dict]) -> RevenueComparisonOutput:
    a_by: dict[str, Decimal] = {}
    b_by: dict[str, Decimal] = {}
    for r in rows:
        period = str(r.get("period") or "").lower()
        key = str(r.get("dimension_key") or r.get("key") or "")
        rev = Decimal(str(r.get("revenue") or 0))
        if period == "a":
            a_by[key] = rev
        elif period == "b":
            b_by[key] = rev
    keys = sorted(set(a_by) | set(b_by))
    deltas = [
        DimensionDelta(
            key=k,
            period_a=a_by.get(k, Decimal(0)),
            period_b=b_by.get(k, Decimal(0)),
            delta=b_by.get(k, Decimal(0)) - a_by.get(k, Decimal(0)),
        )
        for k in keys
    ]
    a_summary = PeriodSummary(
        total=sum(a_by.values(), Decimal(0)),
        by_dimension=[DimensionTotal(key=k, revenue=v) for k, v in sorted(a_by.items())],
    )
    b_summary = PeriodSummary(
        total=sum(b_by.values(), Decimal(0)),
        by_dimension=[DimensionTotal(key=k, revenue=v) for k, v in sorted(b_by.items())],
    )
    return RevenueComparisonOutput(period_a=a_summary, period_b=b_summary, deltas=deltas)


@router.post(
    "/rpc/revenue_comparison",
    response_model=Response[RevenueComparisonOutput],
    tags=["catalog"],
)
async def revenue_comparison(
    request: Request,
    body: RevenueComparisonInput,
    consumer=Depends(require_scope(Scope.GENERAL)),
) -> Response[RevenueComparisonOutput]:
    rows = await execute_card_rows(request, DESCRIPTOR, parameters=_params(body))
    return wrap(request, DESCRIPTOR, _reshape(rows))
