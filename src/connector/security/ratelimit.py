from __future__ import annotations

import json
import logging
import math
from collections.abc import Awaitable, Callable

from limits import parse
from limits.aio.storage import MemoryStorage
from limits.aio.strategies import MovingWindowRateLimiter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from connector.errors import ErrorCode, ErrorEnvelope
from connector.models import ConsumerIdentity, Scope

log = logging.getLogger("connector.ratelimit")


class RateLimitConfig:
    """Resolves a (consumer, scope) tuple to a `limits` RateLimitItem.

    Per spec SEC-04A: per-consumer × per-scope buckets. v1 in-process storage,
    Redis swap is a future config-only change.
    """

    def __init__(
        self,
        *,
        default: str,
        raw_sql: str,
        operator: str,
    ) -> None:
        self._default = parse(default) if default else None
        self._raw_sql = parse(raw_sql) if raw_sql else None
        self._operator = parse(operator) if operator else None

    def for_path(self, path: str, consumer_scope: set[Scope]):
        # Effective scope = the strictest scope this RPC plausibly invokes.
        # Path /rpc/execute_sql -> raw_sql; /rpc/read_audit -> operator; else default.
        if path == "/rpc/execute_sql":
            return self._raw_sql or self._default
        if path == "/rpc/read_audit":
            return self._operator or self._default
        return self._default


def _envelope(code: str, message: str, request_id: str, retry_after_s: int) -> Response:
    body = ErrorEnvelope(code=code, message=message, request_id=request_id).model_dump(
        exclude_none=True
    )
    return Response(
        content=json.dumps(body),
        status_code=429,
        media_type="application/json",
        headers={
            "X-Request-ID": request_id,
            "X-Error-Code": code,
            "Retry-After": str(max(retry_after_s, 1)),
        },
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-consumer × per-scope token-bucket rate limit.

    Runs after auth (consumer is populated). Skips public/health paths and
    pre-auth requests (those are rejected by auth before reaching here).
    """

    def __init__(self, app, *, config: RateLimitConfig) -> None:
        super().__init__(app)
        self._config = config
        self._storage = MemoryStorage()
        self._limiter = MovingWindowRateLimiter(self._storage)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if not path.startswith("/rpc/"):
            return await call_next(request)
        consumer: ConsumerIdentity | None = getattr(request.state, "consumer", None)
        if consumer is None:
            return await call_next(request)

        item = self._config.for_path(path, consumer.scope)
        if item is None:
            return await call_next(request)

        bucket_key = f"{consumer.id}:{path}"
        allowed = await self._limiter.hit(item, bucket_key)
        if not allowed:
            request_id = getattr(request.state, "request_id", "unknown")
            stats = await self._limiter.get_window_stats(item, bucket_key)
            now = stats.reset_time
            retry = max(int(math.ceil(now - _now())), 1) if now else 1
            return _envelope(
                ErrorCode.RATE_LIMITED,
                f"Rate limit exceeded for consumer {consumer.id!r}.",
                request_id,
                retry,
            )
        return await call_next(request)


def _now() -> float:
    import time as _t

    return _t.time()
