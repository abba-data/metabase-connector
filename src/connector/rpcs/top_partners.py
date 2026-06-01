from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator

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


class TopPartnersInput(BaseModel):
    start_date: date
    end_date: date
    limit: int = Field(default=10, ge=1, le=100)
    consolidate: bool = True

    @model_validator(mode="after")
    def _check_dates(self) -> TopPartnersInput:
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
    metabase_card_id=None,
    sql_file="top_partners.sql",
    required_scope=Scope.GENERAL,
)


def _card_params(inp: TopPartnersInput) -> list[dict]:
    return [
        {
            "type": "date/single",
            "target": ["variable", ["template-tag", "start_date"]],
            "value": inp.start_date.isoformat(),
        },
        {
            "type": "date/single",
            "target": ["variable", ["template-tag", "end_date"]],
            "value": inp.end_date.isoformat(),
        },
        {"type": "number/=", "target": ["variable", ["template-tag", "limit"]], "value": inp.limit},
        {
            "type": "category",
            "target": ["variable", ["template-tag", "consolidate"]],
            "value": inp.consolidate,
        },
    ]


_params = _card_params


def _dataset_params(inp: TopPartnersInput) -> list[dict]:
    """Dataset path: consolidate as 'true'/'false' string for {{consolidate}} = 'true' comparisons."""
    return [
        {
            "type": "date/single",
            "target": ["variable", ["template-tag", "start_date"]],
            "value": inp.start_date.isoformat(),
        },
        {
            "type": "date/single",
            "target": ["variable", ["template-tag", "end_date"]],
            "value": inp.end_date.isoformat(),
        },
        {"type": "number/=", "target": ["variable", ["template-tag", "limit"]], "value": inp.limit},
        {
            "type": "category",
            "target": ["variable", ["template-tag", "consolidate"]],
            "value": "true" if inp.consolidate else "false",
        },
    ]


def _dataset_template_tags(inp: TopPartnersInput) -> dict[str, dict[str, Any]]:
    _ = inp
    return {
        "start_date": {"id": "start_date", "name": "start_date", "display-name": "Start date", "type": "date", "required": True},
        "end_date":   {"id": "end_date", "name": "end_date", "display-name": "End date", "type": "date", "required": True},
        "limit":      {"id": "limit", "name": "limit", "display-name": "Limit", "type": "number", "required": True},
        "consolidate": {"id": "consolidate", "name": "consolidate", "display-name": "Consolidate", "type": "text", "required": True},
    }


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
    out_rows: list[TopPartnerRow] = []
    for i, r in enumerate(rows, start=1):
        out_rows.append(
            TopPartnerRow(
                rank=int(r.get("rank") or i),
                partner=str(r.get("partner") or r.get("partner_name") or ""),
                canonical_parent=r.get("canonical_parent"),
                net_revenue=Decimal(str(r.get("net_revenue") or 0)),
            )
        )
    return wrap(request, DESCRIPTOR, TopPartnersOutput(rows=out_rows), via_sql=use_new)
