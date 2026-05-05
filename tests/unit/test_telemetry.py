from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("CONNECTOR_API_KEYS", "tk=u|interactive_script|general,operator")
    import connector.settings as s

    s._settings = None
    from connector.app import create_app
    from connector.audit.store import InMemoryAuditStore

    return TestClient(create_app(audit_store=InMemoryAuditStore()))


def test_metrics_endpoint_public(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")


def test_rpc_calls_increment_request_counter(client: TestClient) -> None:
    client.post(
        "/rpc/describe_catalog",
        headers={"X-Connector-API-Key": "tk"},
        json={},
    )
    body = client.get("/metrics").text
    assert "connector_rpc_requests_total{" in body
    assert 'rpc="describe_catalog"' in body
    assert 'consumer_type="interactive_script"' in body
    assert 'status="success"' in body


def test_unauthenticated_call_records_anonymous_consumer(client: TestClient) -> None:
    client.post("/rpc/describe_catalog", json={})
    body = client.get("/metrics").text
    assert 'consumer_type="anonymous"' in body
    assert 'status="error"' in body


def test_latency_histogram_observes_call(client: TestClient) -> None:
    client.post(
        "/rpc/describe_catalog",
        headers={"X-Connector-API-Key": "tk"},
        json={},
    )
    body = client.get("/metrics").text
    assert "connector_rpc_latency_seconds_bucket" in body
    assert "connector_rpc_latency_seconds_count" in body
