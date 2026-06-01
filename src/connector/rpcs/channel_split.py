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


class ChannelSplitInput(BaseModel):
    start_date: date
    end_date: date
    license_types: list[LicenseTypeLiteral] = Field(default_factory=lambda: ["COMMERCIAL", "ACADEMIC"])

    @model_validator(mode="after")
    def _check_dates(self) -> ChannelSplitInput:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ChannelGroup(BaseModel):
    revenue: Decimal
    line_count: int
    license_count: int


class ChannelSplitOutput(BaseModel):
    partner: ChannelGroup
    direct: ChannelGroup
    total: ChannelGroup


DESCRIPTOR = RpcDescriptor(
    name="channel_split",
    version="1.0.0",
    description="Partner vs direct net-revenue split with line counts and distinct license counts. Channel = partnerName IS NOT NULL.",
    input_model=ChannelSplitInput,
    output_model=ChannelSplitOutput,
    metabase_card_id=None,
    sql_file="channel_split.sql",
    required_scope=Scope.GENERAL,
)


def _card_params(inp: ChannelSplitInput) -> list[dict]:
    """Parameter payload for the legacy card path (list as native list value)."""
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
            "target": ["variable", ["template-tag", "license_types"]],
            "value": list(inp.license_types),
        },
    ]


# Back-compat alias.
_params = _card_params


def _dataset_params(inp: ChannelSplitInput) -> list[dict]:
    """Dataset path passes license_types as a comma-joined string so the SQL
    can use STRING_TO_ARRAY({{license_types}}, ',')."""
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
            "target": ["variable", ["template-tag", "license_types"]],
            "value": ",".join(inp.license_types),
        },
    ]


def _dataset_template_tags(inp: ChannelSplitInput) -> dict[str, dict[str, Any]]:
    _ = inp
    return {
        "start_date": {
            "id": "start_date", "name": "start_date",
            "display-name": "Start date", "type": "date", "required": True,
        },
        "end_date": {
            "id": "end_date", "name": "end_date",
            "display-name": "End date", "type": "date", "required": True,
        },
        "license_types": {
            "id": "license_types", "name": "license_types",
            "display-name": "License types (CSV)", "type": "text", "required": True,
        },
    }


def _row_to_groups(row: dict) -> ChannelSplitOutput:
    """Saved question is expected to return a single row with named columns."""
    partner = ChannelGroup(
        revenue=Decimal(str(row.get("partner_revenue", 0) or 0)),
        line_count=int(row.get("partner_lines", 0) or 0),
        license_count=int(row.get("partner_distinct_licenses", 0) or 0),
    )
    direct = ChannelGroup(
        revenue=Decimal(str(row.get("direct_revenue", 0) or 0)),
        line_count=int(row.get("direct_lines", 0) or 0),
        license_count=int(row.get("direct_distinct_licenses", 0) or 0),
    )
    total = ChannelGroup(
        revenue=partner.revenue + direct.revenue,
        line_count=partner.line_count + direct.line_count,
        license_count=partner.license_count + direct.license_count,
    )
    return ChannelSplitOutput(partner=partner, direct=direct, total=total)


@router.post(
    "/rpc/channel_split",
    response_model=Response[ChannelSplitOutput],
    tags=["catalog"],
)
async def channel_split(
    request: Request,
    body: ChannelSplitInput,
    consumer=Depends(require_scope(Scope.GENERAL)),
) -> Response[ChannelSplitOutput]:
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
    if not rows:
        empty = ChannelGroup(revenue=Decimal(0), line_count=0, license_count=0)
        out = ChannelSplitOutput(partner=empty, direct=empty, total=empty)
    else:
        out = _row_to_groups(rows[0])
    return wrap(request, DESCRIPTOR, out, via_sql=use_new)
