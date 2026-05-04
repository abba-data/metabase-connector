from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ConsumerType(str, Enum):
    BACKEND_SERVICE_ACCOUNT = "backend_service_account"
    INTERACTIVE_SCRIPT = "interactive_script"
    LLM_AGENT = "llm_agent"


class Scope(str, Enum):
    GENERAL = "general"
    RAW_SQL = "raw_sql"
    OPERATOR = "operator"


class ConsumerIdentity(BaseModel):
    id: str = Field(..., description="Stable id used in audit records.")
    name: str = Field(..., description="Human-readable label (cron-job-1, abba-notebook).")
    consumer_type: ConsumerType
    scope: set[Scope]
    rate_limit_class: str = Field(default="default")
