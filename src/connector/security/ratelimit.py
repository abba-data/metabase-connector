"""Per-consumer per-route rate limiting via slowapi.

Per CLAUDE.md: limiter created in the app factory, never at module level.
Bucket key is the ConsumerIdentity.id populated by the auth middleware,
so unauthenticated calls bypass the limiter (auth rejects them first).

slowapi's Limiter is the framework integration; the underlying `limits`
storage handles per-path rate enforcement so we can dispatch by route.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from limits import RateLimitItem, parse
from slowapi import Limiter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from connector.errors import ErrorCode, ErrorEnvelope
from connector.models import ConsumerIdentity


def _consumer_key(request: Request) -> str:
    consumer: ConsumerIdentity | None = getattr(request.state, "consumer", None)
    if consumer is None:
        return "anonymous"
    return consumer.id


def build_limiter() -> Limiter:
    """Construct the app-scoped slowapi Limiter. Attach via
    `app.state.limiter = build_limiter()` in the factory."""
    return Limiter(key_func=_consumer_key)


def _rate_limited_response(request_id: str, message: str, retry_after_s: int = 1) -> Response:
    body = ErrorEnvelope(code=ErrorCode.RATE_LIMITED, message=message, request_id=request_id).model_dump(
        exclude_none=True
    )
    return Response(
        content=json.dumps(body),
        status_code=429,
        media_type="application/json",
        headers={
            "X-Request-ID": request_id,
            "X-Error-Code": ErrorCode.RATE_LIMITED,
            "Retry-After": str(max(retry_after_s, 1)),
        },
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-route rate enforcement using slowapi's Limiter storage."""

    def __init__(
        self,
        app: object,
        *,
        limiter: Limiter,
        default: str,
        raw_sql: str,
        operator: str,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limiter = limiter
        self._items: dict[str, RateLimitItem | None] = {
            "default": parse(default) if default else None,
            "raw_sql": parse(raw_sql) if raw_sql else None,
            "operator": parse(operator) if operator else None,
        }

    def _item_for(self, path: str) -> RateLimitItem | None:
        if path == "/rpc/execute_sql":
            return self._items["raw_sql"] or self._items["default"]
        if path == "/rpc/read_audit":
            return self._items["operator"] or self._items["default"]
        return self._items["default"]

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if not path.startswith("/rpc/"):
            return await call_next(request)
        consumer: ConsumerIdentity | None = getattr(request.state, "consumer", None)
        if consumer is None:
            return await call_next(request)

        item = self._item_for(path)
        if item is None:
            return await call_next(request)

        storage = self._limiter.limiter  # underlying limits storage
        allowed = storage.hit(item, _consumer_key(request), path)
        if not allowed:
            rid = getattr(request.state, "request_id", "unknown")
            return _rate_limited_response(
                rid,
                f"Rate limit exceeded for consumer {_consumer_key(request)!r}.",
            )
        return await call_next(request)
