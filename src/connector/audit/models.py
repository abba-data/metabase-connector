from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from connector.models import ConsumerType, Kind


class AuditStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class AuditRecord(BaseModel):
    timestamp: datetime
    request_id: str
    caller_id: str | None = None
    consumer_type: ConsumerType | None = None
    scope: list[str] = Field(default_factory=list)
    rpc_name: str | None = None
    rpc_version: str | None = None
    parameters: dict[str, Any] | None = None
    kind: Kind | None = None
    source_question_id: int | None = None
    latency_ms: int | None = None
    row_count: int | None = None
    status: AuditStatus
    error_code: str | None = None
    connector_version: str
