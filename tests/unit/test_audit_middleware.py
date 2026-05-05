from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from connector.audit.models import AuditStatus
from connector.audit.store import InMemoryAuditStore
from connector.models import Kind


async def _drain() -> None:
    """Audit writes are fired via asyncio.create_task; let the loop run them."""
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.fixture()
def authed_client_with_audit(monkeypatch) -> tuple[TestClient, InMemoryAuditStore]:
    monkeypatch.setenv(
        "CONNECTOR_API_KEYS",
        "general-key=cron-1|backend_service_account|general;ops-key=ops|backend_service_account|general,operator",
    )
    import connector.settings as s
    s._settings = None
    from connector.app import create_app

    store = InMemoryAuditStore()
    app = create_app(audit_store=store)
    return TestClient(app), store


def test_audit_records_unauthenticated_call(authed_client_with_audit) -> None:
    client, store = authed_client_with_audit
    r = client.post("/rpc/describe_catalog", json={})
    assert r.status_code == 401

    asyncio.run(_drain())
    rows = asyncio.run(store.query())
    assert len(rows) == 1
    rec = rows[0]
    assert rec.rpc_name == "describe_catalog"
    assert rec.status == AuditStatus.ERROR
    assert rec.error_code == "UNAUTHORIZED"
    assert rec.caller_id is None  # auth never populated consumer
    assert rec.latency_ms is not None and rec.latency_ms >= 0


def test_audit_records_successful_call_with_consumer_and_kind(
    authed_client_with_audit,
) -> None:
    client, store = authed_client_with_audit
    r = client.post(
        "/rpc/describe_catalog",
        headers={"X-Connector-API-Key": "general-key"},
        json={},
    )
    assert r.status_code == 200

    asyncio.run(_drain())
    rows = asyncio.run(store.query())
    assert len(rows) == 1
    rec = rows[0]
    assert rec.rpc_name == "describe_catalog"
    assert rec.status == AuditStatus.SUCCESS
    assert rec.caller_id == "cron-1"
    assert rec.consumer_type.value == "backend_service_account"
    assert rec.scope == ["general"]
    assert rec.kind == Kind.CATALOG
    assert rec.rpc_version == "1.0.0"
    assert rec.connector_version
    assert rec.request_id


def test_audit_records_validation_error(authed_client_with_audit) -> None:
    client, store = authed_client_with_audit
    r = client.post(
        "/rpc/partner_revenue",
        headers={"X-Connector-API-Key": "general-key"},
        json={"start_date": "2026-03-01", "end_date": "2026-01-01"},
    )
    assert r.status_code == 422

    asyncio.run(_drain())
    rows = asyncio.run(store.query(rpc_name="partner_revenue"))
    assert len(rows) == 1
    rec = rows[0]
    assert rec.status == AuditStatus.ERROR
    assert rec.error_code == "VALIDATION_ERROR"


def test_audit_redacts_password_like_keys(authed_client_with_audit) -> None:
    client, store = authed_client_with_audit
    # Send a well-formed body with a sensitive-looking key (won't match the input
    # model but Pydantic will reject before audit middleware sees a 200 — what
    # matters is the parameters dict is captured pre-handler).
    client.post(
        "/rpc/describe_catalog",
        headers={"X-Connector-API-Key": "general-key"},
        json={"password": "hunter2", "token": "abc"},
    )
    asyncio.run(_drain())
    rows = asyncio.run(store.query())
    rec = rows[0]
    assert rec.parameters is not None
    assert rec.parameters["password"] == "***"
    assert rec.parameters["token"] == "***"


def test_health_endpoints_not_audited(authed_client_with_audit) -> None:
    client, store = authed_client_with_audit
    client.get("/healthz")
    client.get("/openapi.json")
    asyncio.run(_drain())
    rows = asyncio.run(store.query())
    assert rows == []


def test_read_audit_requires_operator_scope(authed_client_with_audit) -> None:
    client, store = authed_client_with_audit
    # general-key has only 'general' scope.
    r = client.post(
        "/rpc/read_audit",
        headers={"X-Connector-API-Key": "general-key"},
        json={},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "FORBIDDEN"


def test_read_audit_returns_records_for_operator(authed_client_with_audit) -> None:
    client, store = authed_client_with_audit
    # Generate at least one auditable call.
    client.post(
        "/rpc/describe_catalog",
        headers={"X-Connector-API-Key": "general-key"},
        json={},
    )
    asyncio.run(_drain())

    r = client.post(
        "/rpc/read_audit",
        headers={"X-Connector-API-Key": "ops-key"},
        json={"limit": 50},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["kind"] == "catalog"
    records = body["data"]["records"]
    assert any(rec["rpc_name"] == "describe_catalog" for rec in records)
    # The read_audit call itself is also audited.
    asyncio.run(_drain())
    all_rows = asyncio.run(store.query())
    assert any(r.rpc_name == "read_audit" for r in all_rows)
