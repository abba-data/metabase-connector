from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from connector import __version__
from connector.clients.metabase import MetabaseClient
from connector.errors import (
    ConnectorError,
    connector_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from connector.middleware.request_id import RequestIDMiddleware
from connector.registry import registry
from connector.settings import get_settings

log = logging.getLogger("connector.app")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    settings = get_settings()
    if settings.metabase_api_key:
        app.state.metabase = MetabaseClient(
            base_url=settings.metabase_url,
            api_key=settings.metabase_api_key,
            timeout_seconds=settings.metabase_timeout_seconds,
            version_pin=settings.metabase_version_pin or None,
        )
    else:
        app.state.metabase = None
        log.warning("METABASE_API_KEY not set — Metabase client unavailable.")
    try:
        yield
    finally:
        if app.state.metabase is not None:
            await app.state.metabase.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="Modus Data Connector",
        version=__version__,
        description="Typed-RPC HTTP service fronting Metabase.",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIDMiddleware)

    app.add_exception_handler(ConnectorError, connector_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/healthz", tags=["health"])
    async def healthz(request: Request) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "request_id": request.state.request_id,
            "registered_rpcs": [d.name for d in registry.all()],
        }

    @app.get("/healthz/upstream", tags=["health"])
    async def upstream_health(request: Request) -> dict[str, Any]:
        client: MetabaseClient | None = request.app.state.metabase
        if client is None:
            return {"status": "unconfigured", "request_id": request.state.request_id}
        info = await client.health()
        return {
            "status": "ok",
            "metabase": info,
            "request_id": request.state.request_id,
        }

    return app


app = create_app()
