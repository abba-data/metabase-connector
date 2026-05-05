from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from connector.models import Response, Scope
from connector.registry import RpcDescriptor
from connector.rpc_config import CARD_ID_DATA_QUALITY_SIGNALS
from connector.rpcs._helpers import execute_card_rows, wrap
from connector.security.scopes import require_scope

router = APIRouter()


class CheckStatus(str, Enum):
    OK = "OK"
    WATCH = "WATCH"
    ACTION = "ACTION"


class DataQualityCheck(BaseModel):
    check_name: str
    status: CheckStatus
    count_or_sample: Any | None = None
    threshold_context: str | None = None


class DataQualitySignalsInput(BaseModel):
    """No parameters in v1."""


class DataQualitySignalsOutput(BaseModel):
    checks: list[DataQualityCheck]


DESCRIPTOR = RpcDescriptor(
    name="data_quality_signals",
    version="1.0.0",
    description="Per-check data-quality signals (OK/WATCH/ACTION) with supporting count or sample. Same view for consumers and operators.",
    input_model=DataQualitySignalsInput,
    output_model=DataQualitySignalsOutput,
    metabase_card_id=CARD_ID_DATA_QUALITY_SIGNALS,
    required_scope=Scope.GENERAL,
)


def _coerce_status(v: Any) -> CheckStatus:
    if isinstance(v, str):
        u = v.strip().upper()
        if u in {"OK", "PASS"}:
            return CheckStatus.OK
        if u == "WATCH":
            return CheckStatus.WATCH
        if u in {"ACTION", "FAIL"}:
            return CheckStatus.ACTION
    return CheckStatus.WATCH


@router.post(
    "/rpc/data_quality_signals",
    response_model=Response[DataQualitySignalsOutput],
    tags=["catalog"],
)
async def data_quality_signals(
    request: Request,
    body: DataQualitySignalsInput = DataQualitySignalsInput(),
    consumer=Depends(require_scope(Scope.GENERAL)),
) -> Response[DataQualitySignalsOutput]:
    rows = await execute_card_rows(request, DESCRIPTOR)
    checks = [
        DataQualityCheck(
            check_name=str(r.get("check_name") or ""),
            status=_coerce_status(r.get("status")),
            count_or_sample=r.get("count_or_sample"),
            threshold_context=r.get("threshold_context"),
        )
        for r in rows
    ]
    return wrap(request, DESCRIPTOR, DataQualitySignalsOutput(checks=checks))
