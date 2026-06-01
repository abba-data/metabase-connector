"""Tests for the new dbt-marts SQL execution path on each migrated RPC.

These mirror tests/unit/test_rpc_handlers.py but mock execute_dataset (the
native-SQL path) and flip APP_USE_NEW_SQL_* to route handlers through it.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from connector.clients.metabase import MetabaseClient
from connector.rpcs._helpers import _SQL_DIR, load_sql, should_use_new_sql


# ----------------------------------------------------------------------------
# should_use_new_sql logic — pure unit test
# ----------------------------------------------------------------------------

class _FakeDescriptor:
    def __init__(self, name: str, sql_file: str | None, metabase_card_id: int | None) -> None:
        self.name = name
        self.sql_file = sql_file
        self.metabase_card_id = metabase_card_id


class _FakeSettings:
    def __init__(self, **flags: bool) -> None:
        for k, v in flags.items():
            setattr(self, k, v)


def test_should_use_new_sql_returns_false_when_no_sql_file() -> None:
    d = _FakeDescriptor("x", sql_file=None, metabase_card_id=42)
    assert should_use_new_sql(d, _FakeSettings()) is False  # type: ignore[arg-type]


def test_should_use_new_sql_returns_true_when_no_card_and_has_sql() -> None:
    d = _FakeDescriptor("x", sql_file="x.sql", metabase_card_id=None)
    # No legacy fallback possible → always use new path.
    assert should_use_new_sql(d, _FakeSettings()) is True  # type: ignore[arg-type]


def test_should_use_new_sql_honours_per_rpc_flag_when_card_wired() -> None:
    d = _FakeDescriptor("mrr_trend", sql_file="mrr_trend.sql", metabase_card_id=159)
    assert should_use_new_sql(d, _FakeSettings(use_new_sql_mrr_trend=False)) is False  # type: ignore[arg-type]
    assert should_use_new_sql(d, _FakeSettings(use_new_sql_mrr_trend=True)) is True  # type: ignore[arg-type]


def test_load_sql_returns_file_content() -> None:
    d = _FakeDescriptor("mrr_trend", sql_file="mrr_trend.sql", metabase_card_id=None)
    sql = load_sql(d)  # type: ignore[arg-type]
    assert "dbt_marts.mart_mrr_monthly_by_channel" in sql


# ----------------------------------------------------------------------------
# RPC handler tests via the dataset path
# ----------------------------------------------------------------------------

@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("APP_CONNECTOR_API_KEYS", "test-key=cron-1|backend_service_account|general")
    monkeypatch.setenv("APP_METABASE_API_KEY", "stub")
    # Flip every migrated RPC to the new SQL path.
    for rpc in ("mrr_trend", "channel_split", "top_partners", "partner_revenue", "revenue_comparison", "arr_at_risk"):
        monkeypatch.setenv(f"APP_USE_NEW_SQL_{rpc.upper()}", "true")
    # mrr_trend has a default card 159; the env override toggles dataset path on top of it.
    monkeypatch.setenv("APP_CARD_ID_MRR_TREND", "159")
    monkeypatch.setenv("APP_WAREHOUSE_DATABASE_ID", "2")

    from connector.app import create_app
    from connector.settings import load_settings

    load_settings.cache_clear()
    app = create_app()

    captured: dict[str, Any] = {"calls": []}
    canned: dict[str, dict] = {}

    async def fake_execute_dataset(
        self,
        *,
        database_id,
        sql,
        parameters=None,
        template_tags=None,
        timeout=None,
    ):
        captured["calls"].append(
            {
                "database_id": database_id,
                "sql": sql,
                "parameters": parameters,
                "template_tags": template_tags,
            }
        )
        # Match by an identifier-substring in the SQL.
        for marker, payload in canned.items():
            if marker in sql:
                return payload
        return {"data": {"rows": [], "cols": []}}

    monkeypatch.setattr(MetabaseClient, "execute_dataset", fake_execute_dataset)
    app.state.metabase = MetabaseClient(base_url="http://stub", api_key="stub", timeout_seconds=5.0)

    tc = TestClient(app)
    tc.captured = captured  # type: ignore[attr-defined]
    tc.canned = canned  # type: ignore[attr-defined]
    return tc


HEADERS = {"X-Connector-API-Key": "test-key"}


def _stub_dataset(canned: dict[str, dict], marker: str, rows: list[list], col_names: list[str]) -> None:
    canned[marker] = {"data": {"rows": rows, "cols": [{"name": n} for n in col_names]}}


# ---- mrr_trend ---------------------------------------------------------------

def test_mrr_trend_dataset_path_calls_execute_dataset_and_reshapes(client: TestClient) -> None:
    _stub_dataset(
        client.canned,
        "mart_mrr_monthly_by_channel",
        [
            ["2026-01-01", "Direct", "Direct", "1000.00"],
            ["2026-01-01", "Partner", "Partner – Expert", "500.00"],  # noqa: RUF001 (canonical subtype)
            ["2026-02-01", "Direct", "Direct", "1100.00"],
        ],
        ["mrr_month", "customer_type", "partner_type", "mrr"],
    )
    r = client.post("/rpc/mrr_trend", headers=HEADERS, json={"months_back": 12})
    assert r.status_code == 200, r.text
    body = r.json()
    # Envelope flips to dataset path: source_sql_file populated, no card id leaked.
    assert body["meta"]["source_sql_file"] == "mrr_trend.sql"
    assert body["meta"]["source_question_id"] is None
    series = body["data"]["series"]
    assert {pt["month"] for pt in series} == {"2026-01-01", "2026-02-01"}
    jan = next(pt for pt in series if pt["month"] == "2026-01-01")
    assert jan["mrr"] == "1500.00"
    assert jan["by_customer_type"]["Direct"] == "1000.00"
    assert jan["by_partner_type"]["Partner – Expert"] == "500.00"  # noqa: RUF001

    # Confirm execute_dataset was called against db 2 with the right SQL + tags.
    call = client.captured["calls"][-1]
    assert call["database_id"] == 2
    assert "dbt_marts.mart_mrr_monthly_by_channel" in call["sql"]
    assert "months_back" in call["template_tags"]
    assert call["template_tags"]["months_back"]["type"] == "number"


# ---- channel_split -----------------------------------------------------------

def test_channel_split_dataset_path_groups_and_passes_csv_license_types(client: TestClient) -> None:
    _stub_dataset(
        client.canned,
        "int_transactions_enriched",
        [["1200.50", 10, 5, "600.25", 8, 3]],
        [
            "partner_revenue",
            "partner_lines",
            "partner_distinct_licenses",
            "direct_revenue",
            "direct_lines",
            "direct_distinct_licenses",
        ],
    )
    r = client.post(
        "/rpc/channel_split",
        headers=HEADERS,
        json={"start_date": "2024-01-01", "end_date": "2024-12-31"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["source_sql_file"] == "channel_split.sql"
    assert body["data"]["partner"]["revenue"] == "1200.50"
    assert body["data"]["total"]["revenue"] == "1800.75"

    call = client.captured["calls"][-1]
    params_by_name = {
        p["target"][1][1]: p["value"]
        for p in call["parameters"]
    }
    assert params_by_name["license_types"] == "COMMERCIAL,ACADEMIC"
    assert "string_to_array" in call["sql"].lower()


# ---- top_partners ------------------------------------------------------------

def test_top_partners_dataset_path_consolidate_as_string(client: TestClient) -> None:
    _stub_dataset(
        client.canned,
        "int_transactions_enriched",
        [
            [1, "Eficode", "Eficode", "100000"],
            [2, "Adaptavist", "Adaptavist", "80000"],
        ],
        ["rank", "partner", "canonical_parent", "net_revenue"],
    )
    r = client.post(
        "/rpc/top_partners",
        headers=HEADERS,
        json={"start_date": "2024-01-01", "end_date": "2024-12-31", "limit": 5, "consolidate": True},
    )
    assert r.status_code == 200, r.text
    rows = r.json()["data"]["rows"]
    assert rows[0]["partner"] == "Eficode"

    call = client.captured["calls"][-1]
    consolidate = next(
        p["value"] for p in call["parameters"]
        if p["target"][1][1] == "consolidate"
    )
    assert consolidate == "true"  # bool → string for dataset path


# ---- partner_revenue ---------------------------------------------------------

def test_partner_revenue_dataset_path_returns_rows_and_meta(client: TestClient) -> None:
    _stub_dataset(
        client.canned,
        "int_transactions_enriched",
        [
            ["Eficode", "Eficode", "50000", 25, 12],
            ["Adaptavist", "Adaptavist", "40000", 20, 10],
        ],
        ["partner", "canonical_parent", "net_revenue", "line_count", "distinct_license_count"],
    )
    r = client.post(
        "/rpc/partner_revenue",
        headers=HEADERS,
        json={"start_date": "2024-01-01", "end_date": "2024-12-31"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["source_sql_file"] == "partner_revenue.sql"
    assert body["data"]["rows"][0]["partner"] == "Eficode"


# ---- revenue_comparison ------------------------------------------------------

def test_revenue_comparison_dataset_path_reshapes_periods(client: TestClient) -> None:
    _stub_dataset(
        client.canned,
        "int_transactions_enriched",
        [
            ["a", "Direct", "100"],
            ["a", "Partner", "200"],
            ["b", "Direct", "120"],
            ["b", "Partner", "250"],
        ],
        ["period", "dimension_key", "revenue"],
    )
    r = client.post(
        "/rpc/revenue_comparison",
        headers=HEADERS,
        json={"period_a": "Q1 2024", "period_b": "Q1 2025"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    deltas = {d["key"]: d for d in body["data"]["deltas"]}
    assert deltas["Direct"]["delta"] == "20"
    assert deltas["Partner"]["delta"] == "50"
    assert body["data"]["period_a"]["total"] == "300"
    assert body["data"]["period_b"]["total"] == "370"


# ---- arr_at_risk -------------------------------------------------------------

def test_arr_at_risk_dataset_path_totals_and_breakdown(client: TestClient) -> None:
    _stub_dataset(
        client.canned,
        "mart_license_renewal_risk",
        [
            ["Eficode", "10000", 5],
            ["Adaptavist", "8000", 4],
        ],
        ["key", "arr", "license_count"],
    )
    r = client.post(
        "/rpc/arr_at_risk",
        headers=HEADERS,
        json={"horizon_days": 60, "group_by": "partner"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["source_sql_file"] == "arr_at_risk.sql"
    assert body["data"]["total_arr_at_risk"] == "18000"
    assert len(body["data"]["breakdown"]) == 2


# ---- catalog -----------------------------------------------------------------

def test_describe_catalog_surfaces_source_sql_file(client: TestClient) -> None:
    r = client.post("/rpc/describe_catalog", headers=HEADERS, json={})
    assert r.status_code == 200
    rpcs = {e["name"]: e for e in r.json()["data"]["rpcs"]}
    # Migrated RPCs all declare an sql_file.
    for name in ("mrr_trend", "channel_split", "top_partners", "partner_revenue", "revenue_comparison", "arr_at_risk"):
        assert rpcs[name]["source_sql_file"] == f"{name}.sql", name
    # describe_catalog itself is not mart-backed.
    assert rpcs["describe_catalog"]["source_sql_file"] is None


# ---- helper sanity -----------------------------------------------------------

def test_all_migrated_sql_files_exist() -> None:
    for name in ("mrr_trend", "channel_split", "top_partners", "partner_revenue", "revenue_comparison", "arr_at_risk"):
        assert (_SQL_DIR / f"{name}.sql").is_file(), f"missing sql file for {name}"
