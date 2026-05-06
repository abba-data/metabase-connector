from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

log = logging.getLogger("connector.request")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = rid
        # consumer is populated downstream by SEC-01A's auth middleware (or tests).
        if not hasattr(request.state, "consumer"):
            request.state.consumer = None
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response
