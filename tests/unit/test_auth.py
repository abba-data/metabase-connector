from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from connector.security.auth import parse_api_key_config


def test_parse_api_key_config_basic() -> None:
    raw = "k1=cron-1|backend_service_account|general\nk2=nb|interactive_script|general,raw_sql"
    out = parse_api_key_config(raw)
    assert set(out.keys()) == {"k1", "k2"}
    assert out["k1"].consumer_type.value == "backend_service_account"
    assert {s.value for s in out["k1"].scope} == {"general"}
    assert {s.value for s in out["k2"].scope} == {"general", "raw_sql"}


def test_parse_api_key_config_skips_invalid_lines() -> None:
    raw = "# comment\n\nbad-line\nk1=id|backend_service_account|general"
    out = parse_api_key_config(raw)
    assert list(out.keys()) == ["k1"]


@pytest.fixture()
def authed_client(monkeypatch) -> TestClient:
    monkeypatch.setenv(
        "CONNECTOR_API_KEYS", "test-key-1=cron-1|backend_service_account|general"
    )
    # Bust the cached settings.
    import connector.settings as s
    s._settings = None
    from connector.app import create_app
    return TestClient(create_app())


def test_rpc_requires_api_key(authed_client: TestClient) -> None:
    r = authed_client.post("/rpc/describe_catalog", json={})
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"


def test_rpc_rejects_invalid_api_key(authed_client: TestClient) -> None:
    r = authed_client.post(
        "/rpc/describe_catalog", json={}, headers={"X-Connector-API-Key": "wrong"}
    )
    assert r.status_code == 401


def test_describe_catalog_authed(authed_client: TestClient) -> None:
    r = authed_client.post(
        "/rpc/describe_catalog", json={}, headers={"X-Connector-API-Key": "test-key-1"}
    )
    assert r.status_code == 200
    body = r.json()
    assert "data" in body and "meta" in body
    assert body["meta"]["kind"] == "catalog"
    names = [e["name"] for e in body["data"]["rpcs"]]
    assert "describe_catalog" in names
    assert "partner_revenue" in names
    assert "execute_sql" in names
    assert "read_audit" in names
    assert len(names) == 12


def test_healthz_does_not_require_auth(authed_client: TestClient) -> None:
    r = authed_client.get("/healthz")
    assert r.status_code == 200
