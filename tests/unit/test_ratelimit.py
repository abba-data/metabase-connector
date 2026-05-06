from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tight_limit_client(monkeypatch) -> TestClient:
    """Tight default limit (3/minute) so tests trigger 429 quickly."""
    monkeypatch.setenv("APP_CONNECTOR_API_KEYS", "k1=u1|backend_service_account|general")
    monkeypatch.setenv("APP_RATE_LIMIT_DEFAULT", "3/minute")
    monkeypatch.setenv("APP_RATE_LIMIT_RAW_SQL", "1/minute")
    monkeypatch.setenv("APP_RATE_LIMIT_OPERATOR", "5/minute")
    from connector.settings import load_settings

    load_settings.cache_clear()
    from connector.app import create_app
    from connector.audit.store import InMemoryAuditStore

    return TestClient(create_app(audit_store=InMemoryAuditStore()))


HEADERS = {"X-Connector-API-Key": "k1"}


def test_first_n_calls_allowed(tight_limit_client: TestClient) -> None:
    for i in range(3):
        r = tight_limit_client.post("/rpc/describe_catalog", headers=HEADERS, json={})
        assert r.status_code == 200, f"call {i} failed: {r.status_code}"


def test_n_plus_one_call_rate_limited(tight_limit_client: TestClient) -> None:
    for _ in range(3):
        tight_limit_client.post("/rpc/describe_catalog", headers=HEADERS, json={})
    r = tight_limit_client.post("/rpc/describe_catalog", headers=HEADERS, json={})
    assert r.status_code == 429
    body = r.json()
    assert body["code"] == "RATE_LIMITED"
    assert "Retry-After" in r.headers
    assert int(r.headers["Retry-After"]) >= 1


def test_unauthenticated_call_is_not_rate_limited_separately(
    tight_limit_client: TestClient,
) -> None:
    """Auth fires 401 before rate-limit middleware enforces; consumer is None
    so per-consumer bucket is never debited. Auth itself is the rejection."""
    for _ in range(10):
        r = tight_limit_client.post("/rpc/describe_catalog", json={})
        assert r.status_code == 401


def test_health_endpoints_skip_rate_limit(tight_limit_client: TestClient) -> None:
    for _ in range(20):
        r = tight_limit_client.get("/healthz")
        assert r.status_code == 200
