from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

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


LicenseTypeLiteral = Literal["COMMERCIAL", "ACADEMIC"]


class PartnerRevenueInput(BaseModel):
    start_date: date
    end_date: date
    consolidate: bool = True
    license_types: list[LicenseTypeLiteral] = Field(default_factory=lambda: ["COMMERCIAL", "ACADEMIC"])

    @model_validator(mode="after")
    def _check_dates(self) -> PartnerRevenueInput:
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
    metabase_card_id=None,
    sql_file="partner_revenue.sql",
    required_scope=Scope.GENERAL,
)


def _card_params(inp: PartnerRevenueInput) -> list[dict]:
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
        {
            "type": "category",
            "target": ["variable", ["template-tag", "consolidate"]],
            "value": inp.consolidate,
        },
        {
            "type": "category",
            "target": ["variable", ["template-tag", "license_types"]],
            "value": list(inp.license_types),
        },
    ]


_params = _card_params


def _dataset_params(inp: PartnerRevenueInput) -> list[dict]:
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
        {
            "type": "category",
            "target": ["variable", ["template-tag", "consolidate"]],
            "value": "true" if inp.consolidate else "false",
        },
        {
            "type": "category",
            "target": ["variable", ["template-tag", "license_types"]],
            "value": ",".join(inp.license_types),
        },
    ]


def _dataset_template_tags(inp: PartnerRevenueInput) -> dict[str, dict[str, Any]]:
    _ = inp
    return {
        "start_date":    {"id": "start_date",    "name": "start_date",    "display-name": "Start date",        "type": "date",   "required": True},
        "end_date":      {"id": "end_date",      "name": "end_date",      "display-name": "End date",          "type": "date",   "required": True},
        "consolidate":   {"id": "consolidate",   "name": "consolidate",   "display-name": "Consolidate",       "type": "text",   "required": True},
        "license_types": {"id": "license_types", "name": "license_types", "display-name": "License types CSV", "type": "text",   "required": True},
    }


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
    out = PartnerRevenueOutput(rows=[PartnerRevenueRow.model_validate(r) for r in rows])
    return wrap(request, DESCRIPTOR, out, via_sql=use_new)
