from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from connector.models import Scope


class RpcDescriptor(BaseModel):
    name: str = Field(..., description="Catalog RPC name; matches the route path segment.")
    version: str = Field(..., description="Per-RPC semver, bumped on schema change.")
    description: str
    input_model: type[BaseModel] = Field(..., description="Pydantic class.")
    output_model: type[BaseModel] | None = Field(
        default=None, description="Pydantic class for the data payload (Response[T].data)."
    )
    metabase_card_id: int | None = Field(
        default=None, description="Backing Metabase saved-question id; None for runtime-only RPCs."
    )
    required_scope: Scope = Scope.GENERAL
    freshness_window_days: int = 60
    last_updated: datetime | None = None
    deprecated_at: datetime | None = None

    model_config = {"arbitrary_types_allowed": True}


class _Registry:
    def __init__(self) -> None:
        self._rpcs: dict[str, RpcDescriptor] = {}

    def register(self, descriptor: RpcDescriptor) -> RpcDescriptor:
        if descriptor.name in self._rpcs:
            raise ValueError(f"RPC {descriptor.name!r} already registered.")
        self._rpcs[descriptor.name] = descriptor
        return descriptor

    def get(self, name: str) -> RpcDescriptor | None:
        return self._rpcs.get(name)

    def all(self) -> Iterable[RpcDescriptor]:
        return self._rpcs.values()

    def as_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "name": d.name,
                "version": d.version,
                "description": d.description,
                "required_scope": d.required_scope.value,
                "freshness_window_days": d.freshness_window_days,
                "source_question_id": d.metabase_card_id,
                "last_updated": d.last_updated.isoformat() if d.last_updated else None,
                "deprecated_at": d.deprecated_at.isoformat() if d.deprecated_at else None,
                "input_schema": d.input_model.model_json_schema(),
                "output_schema": (
                    d.output_model.model_json_schema() if d.output_model is not None else None
                ),
            }
            for d in self._rpcs.values()
        ]


registry = _Registry()
