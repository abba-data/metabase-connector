from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from connector.models import Kind, Response, Scope, envelope_for
from connector.registry import RpcDescriptor
from connector.rpcs._helpers import get_metabase
from connector.security.scopes import require_scope
from connector.settings import get_settings

router = APIRouter()


# raw_sql_handler: NO connector-side SQL sanitisation. See spec D-017 / SEC-04B.
# Partial sanitisation = false sense of security. Metabase is the only sanitisation surface;
# the audit log (SEC-02) is the safety net.


class MetabaseTemplateTag(BaseModel):
    """Optional Metabase native template tag declaration.

    If your SQL contains `{{var}}` placeholders, declare them here.
    See https://www.metabase.com/learn/sql-questions/sql-variables.
    """

    type: str = Field(..., description="One of: text, number, date, dimension.")
    name: str
    display_name: str | None = None
    required: bool = False
    default: Any | None = None


class ExecuteSqlInput(BaseModel):
    database_id: int = Field(..., description="Metabase database id (see GET /api/database).")
    sql: str = Field(..., min_length=1, description="Native SQL to execute against the database.")
    parameters: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Metabase parameter list, e.g. [{'type':'text','target':[...],'value':'...'}].",
    )
    template_tags: dict[str, MetabaseTemplateTag] | None = Field(
        default=None,
        description="Optional native template-tag declarations keyed by tag name.",
    )


class Column(BaseModel):
    name: str
    base_type: str | None = None
    display_name: str | None = None


class ExecuteSqlOutput(BaseModel):
    columns: list[Column]
    rows: list[list[Any]]
    row_count: int
    running_time_ms: int | None = None
    status: str | None = None
    rows_truncated: int | None = None
    executed_at: datetime


DESCRIPTOR = RpcDescriptor(
    name="execute_sql",
    version="1.0.0",
    description=(
        "Raw-SQL escape hatch. Forwards native SQL to Metabase POST /api/dataset. "
        "No connector-side sanitisation; gated by 'raw_sql' scope. Response envelope kind='raw'."
    ),
    input_model=ExecuteSqlInput,
    output_model=ExecuteSqlOutput,
    metabase_card_id=None,
    required_scope=Scope.RAW_SQL,
    freshness_window_days=60,
)


def _to_columns(cols: list[dict[str, Any]]) -> list[Column]:
    return [
        Column(
            name=str(c.get("name") or ""),
            base_type=c.get("base_type"),
            display_name=c.get("display_name"),
        )
        for c in cols
    ]


@router.post(
    "/rpc/execute_sql",
    response_model=Response[ExecuteSqlOutput],
    tags=["raw"],
)
async def execute_sql(
    request: Request,
    body: ExecuteSqlInput,
    consumer=Depends(require_scope(Scope.RAW_SQL)),
) -> Response[ExecuteSqlOutput]:
    client = get_metabase(request)
    settings = get_settings()

    template_tags = (
        {name: tag.model_dump(exclude_none=True) for name, tag in body.template_tags.items()}
        if body.template_tags
        else None
    )
    payload = await client.execute_dataset(
        database_id=body.database_id,
        sql=body.sql,
        parameters=body.parameters,
        template_tags=template_tags,
        timeout=settings.metabase_timeout_seconds,
    )
    data = payload.get("data") or {}
    cols = _to_columns(data.get("cols") or [])
    rows = list(data.get("rows") or [])
    running_ms_raw = payload.get("running_time")
    out = ExecuteSqlOutput(
        columns=cols,
        rows=rows,
        row_count=int(payload.get("row_count") or len(rows)),
        running_time_ms=int(running_ms_raw) if running_ms_raw is not None else None,
        status=payload.get("status"),
        rows_truncated=data.get("rows_truncated"),
        executed_at=datetime.now(UTC),
    )
    meta = envelope_for(
        request_id=request.state.request_id,
        freshness_window_days=DESCRIPTOR.freshness_window_days,
        source_question_id=None,
        kind=Kind.RAW,
    )
    return Response(data=out, meta=meta)
