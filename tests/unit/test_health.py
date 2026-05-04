from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_returns_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "request_id" in body
    assert "registered_rpcs" in body


def test_request_id_header_round_trip(client: TestClient) -> None:
    r = client.get("/healthz", headers={"X-Request-ID": "req-abc-123"})
    assert r.headers.get("X-Request-ID") == "req-abc-123"
    assert r.json()["request_id"] == "req-abc-123"


def test_request_id_generated_when_absent(client: TestClient) -> None:
    r = client.get("/healthz")
    rid = r.headers.get("X-Request-ID")
    assert rid is not None
    assert len(rid) >= 16
