from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from connector import __version__
from connector.audit.store import AuditStore, build_store
from connector.clients.metabase import MetabaseClient
from connector.errors import (
    ConnectorError,
    connector_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from connector.middleware.audit import AuditMiddleware
from connector.middleware.request_id import RequestIDMiddleware
from connector.registry import registry
from connector.rpcs._registration import register_rpcs
from connector.security.auth import APIKeyAuthMiddleware, parse_api_key_config
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
        if app.state.audit_store is not None:
            await app.state.audit_store.aclose()


def _reset_registry_for_factory() -> None:
    """Tests build the app multiple times; a fresh registry per build avoids duplicate registers."""
    registry._rpcs.clear()  # type: ignore[attr-defined]


def create_app(*, audit_store: AuditStore | None = None) -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    _reset_registry_for_factory()

    app = FastAPI(
        title="Modus Data Connector",
        version=__version__,
        description="Typed-RPC HTTP service fronting Metabase.",
        lifespan=lifespan,
    )

    store: AuditStore = audit_store or build_store(
        settings.audit_store, sqlite_path=settings.audit_db_path
    )
    app.state.audit_store = store

    # Middleware order: outermost runs first. Add inner first.
    # Final flow: RequestID -> Audit -> Auth -> handler.
    app.add_middleware(
        APIKeyAuthMiddleware,
        key_to_identity=parse_api_key_config(settings.connector_api_keys),
    )
    app.add_middleware(AuditMiddleware, store=store)
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

    register_rpcs(app)
    return app


app = create_app()
