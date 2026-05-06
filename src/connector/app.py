from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from loguru import logger
from prometheus_client import generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from starlette.exceptions import HTTPException
from starlette.responses import Response as StarletteResponse

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
from connector.logging_setup import setup_logging
from connector.middleware.audit import AuditMiddleware
from connector.middleware.request_id import RequestIDMiddleware
from connector.middleware.telemetry import TelemetryMiddleware
from connector.observability import setup_datadog
from connector.registry import registry
from connector.rpcs._registration import register_rpcs
from connector.secrets import EnvVarSecretProvider, SecretProvider
from connector.security.auth import APIKeyAuthMiddleware, parse_api_key_config
from connector.security.ratelimit import RateLimitMiddleware, build_limiter
from connector.settings import AppSettings, load_settings
from connector.telemetry import build_registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: AppSettings = app.state.settings
    setup_logging(settings)
    setup_datadog(settings)

    secrets: SecretProvider = app.state.secrets
    api_key = settings.metabase_api_key.get_secret_value() or secrets.get("APP_METABASE_API_KEY")
    if api_key:
        app.state.metabase = MetabaseClient(
            base_url=settings.metabase_url,
            api_key=api_key,
            timeout_seconds=settings.metabase_timeout_seconds,
            version_pin=settings.metabase_version_pin or None,
        )
        logger.info("Metabase client initialised", url=settings.metabase_url)
    else:
        app.state.metabase = None
        logger.warning("APP_METABASE_API_KEY not set; Metabase client unavailable")

    try:
        yield
    finally:
        if app.state.metabase is not None:
            await app.state.metabase.aclose()
        if app.state.audit_store is not None:
            await app.state.audit_store.aclose()


def _reset_registry_for_factory() -> None:
    """Tests build the app multiple times; the registry is module-level
    state and must be re-initialised per factory call. Per CLAUDE.md this
    quasi-global is the only one we accept (registry of registered routes).
    """
    registry._rpcs.clear()


def create_app(
    *,
    settings: AppSettings | None = None,
    audit_store: AuditStore | None = None,
    secrets: SecretProvider | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    _reset_registry_for_factory()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Typed-RPC HTTP service fronting Metabase.",
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.secrets = secrets or EnvVarSecretProvider()

    _attach_security_scheme(app)

    store: AuditStore = audit_store or build_store(settings.audit_store, sqlite_path=settings.audit_db_path)
    app.state.audit_store = store

    metrics_registry, metrics = build_registry()
    app.state.metrics_registry = metrics_registry
    app.state.metrics = metrics

    register_middleware(app, settings, store=store, metrics=metrics)
    register_exception_handlers(app)
    register_health_routes(app)
    register_rpcs(app, settings)
    return app


def register_middleware(
    app: FastAPI,
    settings: AppSettings,
    *,
    store: AuditStore,
    metrics: Any,
) -> None:
    """Per CLAUDE.md: middleware registered in a factory, never at module
    scope. Order: outermost runs first.

    Final flow: RequestID -> Audit -> Telemetry -> Auth -> RateLimit -> handler.
    """
    limiter = build_limiter()
    app.state.limiter = limiter

    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
        default=settings.rate_limit_default,
        raw_sql=settings.rate_limit_raw_sql,
        operator=settings.rate_limit_operator,
    )
    app.add_middleware(
        APIKeyAuthMiddleware,
        key_to_identity=parse_api_key_config(settings.connector_api_keys.get_secret_value()),
    )
    app.add_middleware(TelemetryMiddleware, metrics=metrics)
    app.add_middleware(AuditMiddleware, store=store)
    app.add_middleware(RequestIDMiddleware)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ConnectorError, connector_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)


def register_health_routes(app: FastAPI) -> None:
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

    @app.get("/metrics", tags=["health"], include_in_schema=False)
    async def metrics_endpoint(request: Request) -> StarletteResponse:
        body = generate_latest(request.app.state.metrics_registry)
        return StarletteResponse(content=body, media_type=CONTENT_TYPE_LATEST)


def _attach_security_scheme(app: FastAPI) -> None:
    """Inject the X-Connector-API-Key apiKey scheme into the generated OpenAPI."""
    from fastapi.openapi.utils import get_openapi

    def _custom_openapi() -> dict[str, object]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes["ConnectorApiKey"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-Connector-API-Key",
            "description": (
                "Per-consumer API key. The header value maps to a ConsumerIdentity "
                "(id, consumer_type, scope set) configured via APP_CONNECTOR_API_KEYS."
            ),
        }
        public = {"/healthz", "/healthz/upstream", "/openapi.json", "/docs", "/redoc"}
        for path, item in schema.get("paths", {}).items():
            if path in public:
                continue
            for method, op in item.items():
                if not isinstance(op, dict) or method.lower() not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                }:
                    continue
                op.setdefault("security", [{"ConnectorApiKey": []}])
        app.openapi_schema = schema
        return schema

    app.openapi = _custom_openapi  # type: ignore[method-assign]
