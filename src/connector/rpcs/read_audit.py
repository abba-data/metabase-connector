from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from connector.audit.models import AuditRecord, AuditStatus
from connector.audit.store import AuditStore
from connector.errors import ConnectorError, ErrorCode
from connector.models import Kind, Response, Scope, envelope_for
from connector.registry import RpcDescriptor
from connector.security.scopes import require_scope

router = APIRouter()


class ReadAuditInput(BaseModel):
    start_time: datetime | None = None
    end_time: datetime | None = None
    caller_id: str | None = None
    rpc_name: str | None = None
    kind: Kind | None = None
    status: AuditStatus | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class ReadAuditOutput(BaseModel):
    records: list[AuditRecord]
    next_offset: int | None = None
    queried_at: datetime


DESCRIPTOR = RpcDescriptor(
    name="read_audit",
    version="1.0.0",
    description="Operator-only audit-log read with filters. Returns the structured audit records SEC-02 writes.",
    input_model=ReadAuditInput,
    output_model=ReadAuditOutput,
    metabase_card_id=None,
    required_scope=Scope.OPERATOR,
    freshness_window_days=0,
)


def _get_store(request: Request) -> AuditStore:
    store: AuditStore | None = getattr(request.app.state, "audit_store", None)
    if store is None:
        raise ConnectorError(
            "Audit store not configured.",
            status_code=503,
            code=ErrorCode.METABASE_UNAVAILABLE,
        )
    return store


@router.post(
    "/rpc/read_audit",
    response_model=Response[ReadAuditOutput],
    tags=["operator"],
)
async def read_audit(
    request: Request,
    body: ReadAuditInput,
    consumer=Depends(require_scope(Scope.OPERATOR)),
) -> Response[ReadAuditOutput]:
    store = _get_store(request)
    records = await store.query(
        start_time=body.start_time,
        end_time=body.end_time,
        caller_id=body.caller_id,
        rpc_name=body.rpc_name,
        kind=body.kind,
        status=body.status,
        limit=body.limit,
        offset=body.offset,
    )
    next_offset = body.offset + len(records) if len(records) == body.limit else None
    out = ReadAuditOutput(
        records=records,
        next_offset=next_offset,
        queried_at=datetime.now(UTC),
    )
    meta = envelope_for(
        request_id=request.state.request_id,
        freshness_window_days=DESCRIPTOR.freshness_window_days,
        source_question_id=None,
    )
    return Response(data=out, meta=meta)
