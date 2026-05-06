from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from connector.clients.metabase import MetabaseClient


@pytest.fixture()
def general_only_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("APP_CONNECTOR_API_KEYS", "key-general=cron|backend_service_account|general")
    monkeypatch.setenv("APP_METABASE_API_KEY", "stub")
    from connector.settings import load_settings

    load_settings.cache_clear()
    from connector.app import create_app

    app = create_app()
    app.state.metabase = MetabaseClient(base_url="http://metabase.test", api_key="stub", timeout_seconds=5.0)
    return TestClient(app)


@pytest.fixture()
def raw_sql_client(monkeypatch) -> TestClient:
    monkeypatch.setenv(
        "APP_CONNECTOR_API_KEYS",
        "key-raw=ana|interactive_script|general,raw_sql",
    )
    monkeypatch.setenv("APP_METABASE_API_KEY", "stub")
    from connector.settings import load_settings

    load_settings.cache_clear()
    from connector.app import create_app

    app = create_app()
    app.state.metabase = MetabaseClient(base_url="http://metabase.test", api_key="stub", timeout_seconds=5.0)
    return TestClient(app)


def test_execute_sql_requires_api_key(general_only_client: TestClient) -> None:
    r = general_only_client.post("/rpc/execute_sql", json={"database_id": 2, "sql": "SELECT 1"})
    assert r.status_code == 401


def test_execute_sql_blocks_general_only(general_only_client: TestClient) -> None:
    r = general_only_client.post(
        "/rpc/execute_sql",
        headers={"X-Connector-API-Key": "key-general"},
        json={"database_id": 2, "sql": "SELECT 1"},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "FORBIDDEN"


@respx.mock
def test_execute_sql_success_returns_columns_rows_envelope(raw_sql_client: TestClient) -> None:
    payload = {
        "data": {
            "rows": [[1, "alpha"], [2, "beta"]],
            "cols": [
                {"name": "id", "base_type": "type/Integer", "display_name": "ID"},
                {"name": "label", "base_type": "type/Text"},
            ],
            "rows_truncated": None,
        },
        "row_count": 2,
        "running_time": 12,
        "status": "completed",
    }
    route = respx.post("http://metabase.test/api/dataset").mock(return_value=httpx.Response(200, json=payload))
    r = raw_sql_client.post(
        "/rpc/execute_sql",
        headers={"X-Connector-API-Key": "key-raw"},
        json={
            "database_id": 2,
            "sql": "SELECT id, label FROM widgets ORDER BY id LIMIT 2",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["kind"] == "raw"
    assert body["meta"]["source_question_id"] is None
    data = body["data"]
    assert data["row_count"] == 2
    assert data["running_time_ms"] == 12
    assert data["status"] == "completed"
    assert [c["name"] for c in data["columns"]] == ["id", "label"]
    assert data["rows"] == [[1, "alpha"], [2, "beta"]]

    # SQL is forwarded verbatim to Metabase.
    assert route.called
    sent = route.calls.last.request.read()
    assert b"SELECT id, label FROM widgets" in sent
    assert b'"type": "native"' in sent or b'"type":"native"' in sent
    assert b'"database": 2' in sent or b'"database":2' in sent


@respx.mock
def test_execute_sql_passes_template_tags_and_parameters(raw_sql_client: TestClient) -> None:
    respx.post("http://metabase.test/api/dataset").mock(
        return_value=httpx.Response(200, json={"data": {"rows": [], "cols": []}, "row_count": 0})
    )
    r = raw_sql_client.post(
        "/rpc/execute_sql",
        headers={"X-Connector-API-Key": "key-raw"},
        json={
            "database_id": 2,
            "sql": "SELECT * FROM t WHERE created_at >= {{since}}",
            "template_tags": {"since": {"type": "date", "name": "since", "required": True}},
            "parameters": [
                {
                    "type": "date/single",
                    "target": ["variable", ["template-tag", "since"]],
                    "value": "2026-01-01",
                }
            ],
        },
    )
    assert r.status_code == 200, r.text


@respx.mock
def test_execute_sql_propagates_metabase_4xx_as_metabase_error(raw_sql_client: TestClient) -> None:
    respx.post("http://metabase.test/api/dataset").mock(
        return_value=httpx.Response(400, text="syntax error at end of input")
    )
    r = raw_sql_client.post(
        "/rpc/execute_sql",
        headers={"X-Connector-API-Key": "key-raw"},
        json={"database_id": 2, "sql": "SELECT * FROM"},
    )
    assert r.status_code == 502
    assert r.json()["code"] == "METABASE_ERROR"


@respx.mock
def test_execute_sql_propagates_metabase_5xx_as_unavailable(raw_sql_client: TestClient) -> None:
    respx.post("http://metabase.test/api/dataset").mock(return_value=httpx.Response(503, text="upstream down"))
    r = raw_sql_client.post(
        "/rpc/execute_sql",
        headers={"X-Connector-API-Key": "key-raw"},
        json={"database_id": 2, "sql": "SELECT 1"},
    )
    assert r.status_code == 503
    assert r.json()["code"] == "METABASE_UNAVAILABLE"


@respx.mock
def test_execute_sql_propagates_202_as_exceeded_sync_window(raw_sql_client: TestClient) -> None:
    respx.post("http://metabase.test/api/dataset").mock(return_value=httpx.Response(202, json={}))
    r = raw_sql_client.post(
        "/rpc/execute_sql",
        headers={"X-Connector-API-Key": "key-raw"},
        json={"database_id": 2, "sql": "SELECT 1"},
    )
    assert r.status_code == 504
    assert r.json()["code"] == "EXCEEDED_SYNC_WINDOW"


def test_execute_sql_rejects_empty_sql(raw_sql_client: TestClient) -> None:
    r = raw_sql_client.post(
        "/rpc/execute_sql",
        headers={"X-Connector-API-Key": "key-raw"},
        json={"database_id": 2, "sql": ""},
    )
    assert r.status_code == 422
