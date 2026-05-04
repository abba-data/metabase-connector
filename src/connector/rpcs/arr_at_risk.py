from __future__ import annotations

from decimal import Decimal
from enum import Enum

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from connector.models import Response, Scope
from connector.registry import RpcDescriptor
from connector.rpc_config import CARD_ID_ARR_AT_RISK
from connector.rpcs._helpers import execute_card_rows, wrap
from connector.security.scopes import require_scope

router = APIRouter()


class GroupBy(str, Enum):
    OVERALL = "overall"
    PARTNER = "partner"
    APP = "app"


class ArrAtRiskInput(BaseModel):
    horizon_days: int = Field(default=60, ge=1, le=730)
    group_by: GroupBy = GroupBy.OVERALL


class AtRiskBucket(BaseModel):
    key: str
    arr: Decimal
    license_count: int


class ArrAtRiskOutput(BaseModel):
    total_arr_at_risk: Decimal
    breakdown: list[AtRiskBucket]


DESCRIPTOR = RpcDescriptor(
    name="arr_at_risk",
    version="1.0.0",
    description="Licenses whose maintenanceEndDate falls within horizon_days, broken down by overall/partner/app.",
    input_model=ArrAtRiskInput,
    output_model=ArrAtRiskOutput,
    metabase_card_id=CARD_ID_ARR_AT_RISK,
    required_scope=Scope.GENERAL,
)


def _params(inp: ArrAtRiskInput) -> list[dict]:
    return [
        {"type": "number/=", "target": ["variable", ["template-tag", "horizon_days"]], "value": inp.horizon_days},
        {"type": "category", "target": ["variable", ["template-tag", "group_by"]], "value": inp.group_by.value},
    ]


@router.post(
    "/rpc/arr_at_risk",
    response_model=Response[ArrAtRiskOutput],
    tags=["catalog"],
)
async def arr_at_risk(
    request: Request,
    body: ArrAtRiskInput,
    consumer=Depends(require_scope(Scope.GENERAL)),
) -> Response[ArrAtRiskOutput]:
    rows = await execute_card_rows(request, DESCRIPTOR, parameters=_params(body))
    breakdown: list[AtRiskBucket] = []
    total = Decimal(0)
    for r in rows:
        bucket = AtRiskBucket(
            key=str(r.get("key") or r.get("group_key") or "overall"),
            arr=Decimal(str(r.get("arr") or r.get("arr_at_risk") or 0)),
            license_count=int(r.get("license_count") or r.get("licenses_at_risk") or 0),
        )
        breakdown.append(bucket)
        total += bucket.arr
    out = ArrAtRiskOutput(total_arr_at_risk=total, breakdown=breakdown)
    return wrap(request, DESCRIPTOR, out)
