from __future__ import annotations

from typing import Any

from fastapi import Request

from connector.clients.metabase import MetabaseClient
from connector.errors import ConnectorError, ErrorCode
from connector.models import Kind, Response, ResponseMeta, envelope_for
from connector.registry import RpcDescriptor
from connector.rows import metabase_rows_as_dicts
from connector.settings import get_settings


def get_metabase(request: Request) -> MetabaseClient:
    client: MetabaseClient | None = request.app.state.metabase
    if client is None:
        raise ConnectorError(
            "Metabase client not configured (METABASE_API_KEY missing).",
            status_code=503,
            code=ErrorCode.METABASE_UNAVAILABLE,
        )
    return client


def make_meta(request: Request, descriptor: RpcDescriptor) -> ResponseMeta:
    return envelope_for(
        request_id=request.state.request_id,
        freshness_window_days=descriptor.freshness_window_days,
        source_question_id=descriptor.metabase_card_id,
        kind=Kind.CATALOG,
    )


async def execute_card_rows(
    request: Request,
    descriptor: RpcDescriptor,
    parameters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if descriptor.metabase_card_id is None:
        raise ConnectorError(
            f"RPC {descriptor.name!r} has no Metabase card_id wired.",
            status_code=503,
            code=ErrorCode.METABASE_UNAVAILABLE,
        )
    client = get_metabase(request)
    settings = get_settings()
    payload = await client.execute_card(
        descriptor.metabase_card_id,
        parameters=parameters,
        timeout=settings.metabase_timeout_seconds,
    )
    return metabase_rows_as_dicts(payload)


def wrap(request: Request, descriptor: RpcDescriptor, data: Any) -> Response:
    return Response(data=data, meta=make_meta(request, descriptor))
