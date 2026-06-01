from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Request

from connector.errors import ConnectorError, ErrorCode
from connector.models import Kind, Response, ResponseMeta, envelope_for

if TYPE_CHECKING:
    from connector.clients.metabase import MetabaseClient
    from connector.registry import RpcDescriptor
    from connector.settings import AppSettings


_SQL_DIR = Path(__file__).parent / "sql"


def get_metabase(request: Request) -> MetabaseClient:
    client: MetabaseClient | None = request.app.state.metabase
    if client is None:
        raise ConnectorError(
            "Metabase client not configured (APP_METABASE_API_KEY missing).",
            status_code=503,
            code=ErrorCode.METABASE_UNAVAILABLE,
        )
    return client


def get_settings_from_request(request: Request) -> AppSettings:
    return request.app.state.settings


def make_meta(request: Request, descriptor: RpcDescriptor, *, via_sql: bool | None = None) -> ResponseMeta:
    """Build the response envelope.

    `via_sql` reports which execution path actually produced this response:
      - True  → source_sql_file populated, source_question_id null (mart-backed).
      - False → source_question_id populated, source_sql_file null (card-backed).
      - None  → no execution happened (e.g. describe_catalog); fall back to
                descriptor metadata, which is fine because no row data was returned.
    """
    if via_sql is True:
        source_question_id: int | None = None
        source_sql_file: str | None = descriptor.sql_file
    elif via_sql is False:
        source_question_id = descriptor.metabase_card_id
        source_sql_file = None
    else:
        source_question_id = descriptor.metabase_card_id
        source_sql_file = descriptor.sql_file
    return envelope_for(
        request_id=request.state.request_id,
        freshness_window_days=descriptor.freshness_window_days,
        source_question_id=source_question_id,
        source_sql_file=source_sql_file,
        kind=Kind.CATALOG,
    )


def should_use_new_sql(descriptor: RpcDescriptor, settings: AppSettings) -> bool:
    """Decide which execution path an RPC takes.

    Logic:
      - If the descriptor has no `sql_file`, never use the new path (impossible).
      - If the descriptor has no `metabase_card_id`, the new SQL path is the
        only option — use it (no card to fall back to).
      - Otherwise honour the per-RPC `use_new_sql_<name>` setting (default False).
    """
    if descriptor.sql_file is None:
        return False
    if descriptor.metabase_card_id is None:
        return True
    return bool(getattr(settings, f"use_new_sql_{descriptor.name}", False))


def load_sql(descriptor: RpcDescriptor) -> str:
    if descriptor.sql_file is None:
        raise ConnectorError(
            f"RPC {descriptor.name!r} has no sql_file declared.",
            status_code=503,
            code=ErrorCode.METABASE_UNAVAILABLE,
        )
    path = _SQL_DIR / descriptor.sql_file
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConnectorError(
            f"RPC {descriptor.name!r}: sql_file {descriptor.sql_file!r} not found at {path}.",
            status_code=500,
            code=ErrorCode.METABASE_UNAVAILABLE,
        ) from exc


async def execute_card_rows(
    request: Request,
    descriptor: RpcDescriptor,
    parameters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if descriptor.metabase_card_id is None:
        raise ConnectorError(
            f"RPC {descriptor.name!r} has no Metabase card_id wired (set APP_CARD_ID_{descriptor.name.upper()}).",
            status_code=503,
            code=ErrorCode.METABASE_UNAVAILABLE,
        )
    client = get_metabase(request)
    settings = get_settings_from_request(request)
    payload = await client.execute_card(
        descriptor.metabase_card_id,
        parameters=parameters,
        timeout=settings.metabase_timeout_seconds,
    )
    from connector.rows import metabase_rows_as_dicts

    return metabase_rows_as_dicts(payload)


async def execute_dataset_rows(
    request: Request,
    descriptor: RpcDescriptor,
    *,
    template_tags: dict[str, dict[str, Any]] | None = None,
    parameters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run a native-SQL query stored at `descriptor.sql_file` against the
    warehouse via Metabase's /api/dataset endpoint, returning row-dicts.
    """
    sql = load_sql(descriptor)
    client = get_metabase(request)
    settings = get_settings_from_request(request)
    payload = await client.execute_dataset(
        database_id=settings.warehouse_database_id,
        sql=sql,
        template_tags=template_tags,
        parameters=parameters,
        timeout=settings.metabase_timeout_seconds,
    )
    from connector.rows import metabase_rows_as_dicts

    return metabase_rows_as_dicts(payload)


def wrap(
    request: Request,
    descriptor: RpcDescriptor,
    data: Any,
    *,
    via_sql: bool | None = None,
) -> Response[Any]:
    return Response(data=data, meta=make_meta(request, descriptor, via_sql=via_sql))
