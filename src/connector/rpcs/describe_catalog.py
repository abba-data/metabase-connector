from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from connector.models import Response, Scope
from connector.registry import RpcDescriptor, registry
from connector.rpcs._helpers import wrap
from connector.security.scopes import require_scope

router = APIRouter()


class DescribeCatalogInput(BaseModel):
    """describe_catalog has no parameters."""


class CatalogEntry(BaseModel):
    name: str
    version: str
    description: str
    required_scope: str
    freshness_window_days: int
    source_question_id: int | None = None
    last_updated: datetime | None = None
    deprecated_at: datetime | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None


class DescribeCatalogOutput(BaseModel):
    rpcs: list[CatalogEntry]
    generated_at: datetime


DESCRIPTOR = RpcDescriptor(
    name="describe_catalog",
    version="1.0.0",
    description="List all catalog RPCs with input/output JSON Schema, version, scope, and freshness.",
    input_model=DescribeCatalogInput,
    output_model=DescribeCatalogOutput,
    metabase_card_id=None,
    required_scope=Scope.GENERAL,
    freshness_window_days=0,
)


@router.post(
    "/rpc/describe_catalog",
    response_model=Response[DescribeCatalogOutput],
    tags=["catalog"],
)
async def describe_catalog(
    request: Request,
    _: DescribeCatalogInput = DescribeCatalogInput(),
    consumer=Depends(require_scope(Scope.GENERAL)),
) -> Response[DescribeCatalogOutput]:
    entries = [CatalogEntry.model_validate(e) for e in registry.as_catalog()]
    out = DescribeCatalogOutput(rpcs=entries, generated_at=datetime.now(timezone.utc))
    return wrap(request, DESCRIPTOR, out)
