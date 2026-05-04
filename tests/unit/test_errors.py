from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from connector.errors import (
    ConnectorError,
    ErrorCode,
    UnauthorizedError,
    connector_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from connector.middleware.request_id import RequestIDMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(ConnectorError, connector_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    class Body(BaseModel):
        n: int

    @app.post("/echo")
    async def echo(body: Body) -> dict[str, int]:
        return {"n": body.n}

    @app.get("/boom-connector")
    async def boom_connector() -> None:
        raise UnauthorizedError("nope")

    @app.get("/boom-http")
    async def boom_http() -> None:
        raise HTTPException(status_code=404, detail="missing")

    @app.get("/boom-unhandled")
    async def boom_unhandled() -> None:
        raise RuntimeError("explode")

    return app


def test_connector_error_returns_typed_envelope() -> None:
    client = TestClient(_build_app())
    r = client.get("/boom-connector")
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == ErrorCode.UNAUTHORIZED
    assert body["message"] == "nope"
    assert "request_id" in body


def test_validation_error_returns_typed_envelope() -> None:
    client = TestClient(_build_app())
    r = client.post("/echo", json={"n": "not-an-int"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == ErrorCode.VALIDATION_ERROR
    assert "request_id" in body
    assert body["debug"]["errors"]


def test_http_exception_returns_typed_envelope() -> None:
    client = TestClient(_build_app())
    r = client.get("/boom-http")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == ErrorCode.NOT_FOUND


def test_unhandled_exception_returns_typed_envelope() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)
    r = client.get("/boom-unhandled")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == ErrorCode.INTERNAL_ERROR
