from __future__ import annotations

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Kind(str, Enum):
    CATALOG = "catalog"
    RAW = "raw"


class ResponseMeta(BaseModel):
    freshness_window_days: int = Field(
        ...,
        description="Atlassian eventual-consistency window. Recent data within this window may shift on re-run.",
    )
    source_question_id: int | None = Field(
        default=None,
        description="Metabase saved-question id that produced this result. Null for raw-SQL or dbt-mart-backed RPCs.",
    )
    source_sql_file: str | None = Field(
        default=None,
        description="Filename under src/connector/rpcs/sql/ that produced this result. Null for card-backed RPCs.",
    )
    kind: Kind = Field(default=Kind.CATALOG)
    request_id: str = Field(..., description="Per-request id; threaded into logs and audit.")


class Response(BaseModel, Generic[T]):
    data: T
    meta: ResponseMeta


def envelope_for(
    *,
    request_id: str,
    freshness_window_days: int,
    source_question_id: int | None = None,
    source_sql_file: str | None = None,
    kind: Kind = Kind.CATALOG,
) -> ResponseMeta:
    return ResponseMeta(
        freshness_window_days=freshness_window_days,
        source_question_id=source_question_id,
        source_sql_file=source_sql_file,
        kind=kind,
        request_id=request_id,
    )
