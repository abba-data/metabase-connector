from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from connector.errors import ErrorCode, ErrorEnvelope
from connector.models import ConsumerIdentity, ConsumerType, Scope

API_KEY_HEADER = "X-Connector-API-Key"

log = logging.getLogger("connector.auth")


def parse_api_key_config(raw: str) -> dict[str, ConsumerIdentity]:
    """Parse `CONNECTOR_API_KEYS` env into a {api_key -> ConsumerIdentity} map.

    Format: comma-separated entries of `api_key=consumer_id|consumer_type|scope1,scope2[|rate_limit_class]`.
    Whitespace tolerated. Lines beginning with `#` ignored.

    Example:
      dev-key-1=cron-1|backend_service_account|general
      dev-key-2=abba-notebook|interactive_script|general,raw_sql
    """
    out: dict[str, ConsumerIdentity] = {}
    if not raw:
        return out
    # split on commas only when they're outside the inline scope list — easiest with newlines
    for line in raw.replace(";", "\n").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            log.warning("Skipping malformed CONNECTOR_API_KEYS entry (no '='): %r", line)
            continue
        key, _, rest = line.partition("=")
        key = key.strip()
        parts = [p.strip() for p in rest.split("|")]
        if len(parts) < 3:
            log.warning("Skipping malformed CONNECTOR_API_KEYS entry: %r", line)
            continue
        consumer_id = parts[0]
        try:
            consumer_type = ConsumerType(parts[1])
        except ValueError:
            log.warning("Unknown consumer_type %r in CONNECTOR_API_KEYS entry %r", parts[1], line)
            continue
        scopes: set[Scope] = set()
        for s in parts[2].split(","):
            s = s.strip()
            if not s:
                continue
            try:
                scopes.add(Scope(s))
            except ValueError:
                log.warning("Unknown scope %r in CONNECTOR_API_KEYS entry %r", s, line)
        rate_limit_class = parts[3] if len(parts) > 3 and parts[3] else "default"
        out[key] = ConsumerIdentity(
            id=consumer_id,
            name=consumer_id,
            consumer_type=consumer_type,
            scope=scopes,
            rate_limit_class=rate_limit_class,
        )
    return out


# Routes that bypass auth (health, openapi, docs).
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/healthz",
        "/healthz/upstream",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/docs/oauth2-redirect",
        "/metrics",
    }
)


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return path.startswith("/docs") or path.startswith("/redoc")


def _envelope(code: str, message: str, request_id: str, status: int) -> Response:
    body = ErrorEnvelope(code=code, message=message, request_id=request_id).model_dump(
        exclude_none=True
    )
    import json

    return Response(
        content=json.dumps(body),
        status_code=status,
        media_type="application/json",
        headers={"X-Request-ID": request_id, "X-Error-Code": code},
    )


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, key_to_identity: dict[str, ConsumerIdentity]) -> None:
        super().__init__(app)
        self._keys = key_to_identity

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)
        rid = getattr(request.state, "request_id", "unknown")
        provided = request.headers.get(API_KEY_HEADER)
        if not provided:
            return _envelope(
                ErrorCode.UNAUTHORIZED,
                f"Missing {API_KEY_HEADER} header.",
                rid,
                401,
            )
        identity = self._keys.get(provided)
        if identity is None:
            return _envelope(
                ErrorCode.UNAUTHORIZED,
                "Invalid API key.",
                rid,
                401,
            )
        request.state.consumer = identity
        return await call_next(request)
