from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from connector import __version__
from connector.audit.models import AuditRecord, AuditStatus
from connector.audit.store import AuditStore
from connector.models import ConsumerIdentity, Kind
from connector.registry import registry

log = logging.getLogger("connector.audit.mw")

_AUDIT_PATH_PREFIX = "/rpc/"


def _rpc_name_from_path(path: str) -> str | None:
    if not path.startswith(_AUDIT_PATH_PREFIX):
        return None
    name = path[len(_AUDIT_PATH_PREFIX) :].split("/", 1)[0].split("?", 1)[0]
    return name or None


async def _read_body(request: Request) -> bytes:
    """Read body once and stash for downstream re-read.

    Starlette's request._receive can only be consumed once; we replace it
    with a closure that replays the bytes so the handler still sees the body.
    """
    body = await request.body()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive  # type: ignore[attr-defined]
    return body


def _safe_json(body: bytes) -> dict[str, Any] | None:
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _redact(parameters: dict[str, Any] | None) -> dict[str, Any] | None:
    """Redact sensitive-looking keys before persisting. Conservative — keep
    most analytical parameters (dates, ids, partner names) for compliance value.
    """
    if not parameters:
        return parameters
    redacted: dict[str, Any] = {}
    for k, v in parameters.items():
        if k.lower() in {"password", "secret", "token", "api_key"}:
            redacted[k] = "***"
        else:
            redacted[k] = v
    return redacted


class AuditMiddleware(BaseHTTPMiddleware):
    """Records every /rpc/* call. Outermost so 401/403 are also captured.

    Audit write happens off the response hot path via asyncio.create_task —
    durability trade-off documented at SEC-02B: in the event of crash mid-write,
    the most recent record may be lost. Acceptable for SOC v1 per spec.
    """

    def __init__(self, app, *, store: AuditStore) -> None:
        super().__init__(app)
        self._store = store

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if not path.startswith(_AUDIT_PATH_PREFIX):
            return await call_next(request)

        rpc_name = _rpc_name_from_path(path)
        body_bytes = await _read_body(request)
        parameters = _redact(_safe_json(body_bytes))

        start = time.perf_counter()
        response: Response | None = None
        error_code: str | None = None
        try:
            response = await call_next(request)
        except Exception as e:
            error_code = type(e).__name__
            raise
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            consumer: ConsumerIdentity | None = getattr(request.state, "consumer", None)
            request_id = getattr(request.state, "request_id", "unknown")

            if response is not None and 400 <= response.status_code < 600:
                error_code = (
                    response.headers.get("X-Error-Code") or error_code or _peek_error_code(response)
                )

            descriptor = registry.get(rpc_name) if rpc_name else None
            kind: Kind | None = None
            source_question_id: int | None = None
            if descriptor is not None:
                source_question_id = descriptor.metabase_card_id
                kind = Kind.RAW if descriptor.name == "execute_sql" else Kind.CATALOG

            row_count = getattr(request.state, "audit_row_count", None)

            status_ok = response is not None and 200 <= response.status_code < 400
            record = AuditRecord(
                timestamp=datetime.now(UTC),
                request_id=request_id,
                caller_id=consumer.id if consumer else None,
                consumer_type=consumer.consumer_type if consumer else None,
                scope=sorted(s.value for s in consumer.scope) if consumer else [],
                rpc_name=rpc_name,
                rpc_version=descriptor.version if descriptor else None,
                parameters=parameters,
                kind=kind,
                source_question_id=source_question_id,
                latency_ms=latency_ms,
                row_count=row_count,
                status=AuditStatus.SUCCESS if status_ok else AuditStatus.ERROR,
                error_code=error_code if not status_ok else None,
                connector_version=__version__,
            )
            asyncio.create_task(_write(self._store, record))

        return response  # type: ignore[return-value]


def _peek_error_code(response: Response) -> str | None:
    """Best-effort extraction of `code` from a JSONResponse error envelope."""
    body = getattr(response, "body", None)
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("code"), str):
        return parsed["code"]
    return None


async def _write(store: AuditStore, record: AuditRecord) -> None:
    try:
        await store.write(record)
    except Exception as e:
        log.exception("audit write failed: %s", e)
