from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from connector.errors import (
    ConnectorError,
    connector_error_handler,
)
from connector.middleware.request_id import RequestIDMiddleware
from connector.models import ConsumerIdentity, ConsumerType, Scope
from connector.security.scopes import require_scope


def _build(app_consumer: ConsumerIdentity | None) -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(ConnectorError, connector_error_handler)  # type: ignore[arg-type]

    @app.middleware("http")
    async def inject(request: Request, call_next):
        request.state.consumer = app_consumer
        return await call_next(request)

    @app.get("/general")
    async def general(c=Depends(require_scope(Scope.GENERAL))) -> dict:
        return {"ok": True}

    @app.get("/operator")
    async def operator(c=Depends(require_scope(Scope.OPERATOR))) -> dict:
        return {"ok": True}

    return TestClient(app)


def _identity(*scopes: Scope) -> ConsumerIdentity:
    return ConsumerIdentity(
        id="u1",
        name="u1",
        consumer_type=ConsumerType.BACKEND_SERVICE_ACCOUNT,
        scope=set(scopes),
    )


def test_general_scope_allowed() -> None:
    c = _build(_identity(Scope.GENERAL))
    assert c.get("/general").status_code == 200


def test_general_only_blocked_from_operator() -> None:
    c = _build(_identity(Scope.GENERAL))
    r = c.get("/operator")
    assert r.status_code == 403
    assert r.json()["code"] == "FORBIDDEN"


def test_operator_can_access_operator() -> None:
    c = _build(_identity(Scope.OPERATOR))
    assert c.get("/operator").status_code == 200


def test_no_consumer_yields_unauthorized() -> None:
    c = _build(None)
    assert c.get("/general").status_code == 401
