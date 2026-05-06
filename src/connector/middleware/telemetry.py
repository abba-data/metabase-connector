from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from connector.models import ConsumerIdentity
from connector.telemetry import Metrics

_RPC_PREFIX = "/rpc/"


def _rpc_name(path: str) -> str | None:
    if not path.startswith(_RPC_PREFIX):
        return None
    name = path[len(_RPC_PREFIX) :].split("/", 1)[0].split("?", 1)[0]
    return name or None


class TelemetryMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, metrics: Metrics) -> None:
        super().__init__(app)
        self._metrics = metrics

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rpc = _rpc_name(request.url.path)
        if rpc is None:
            return await call_next(request)

        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response  # noqa: RET504  finally clause needs the variable
        finally:
            elapsed = time.perf_counter() - start
            consumer: ConsumerIdentity | None = getattr(request.state, "consumer", None)
            consumer_type = consumer.consumer_type.value if consumer else "anonymous"
            status = "success" if response is not None and 200 <= response.status_code < 400 else "error"
            self._metrics.requests_total.labels(rpc=rpc, consumer_type=consumer_type, status=status).inc()
            self._metrics.latency_seconds.labels(rpc=rpc, consumer_type=consumer_type).observe(elapsed)
