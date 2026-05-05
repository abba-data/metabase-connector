from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from connector.clients.metabase import MetabaseClient


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("CONNECTOR_API_KEYS", "test-key=cron-1|backend_service_account|general")
    monkeypatch.setenv("METABASE_API_KEY", "stub")
    monkeypatch.setenv("CARD_ID_PARTNER_REVENUE", "1001")
    monkeypatch.setenv("CARD_ID_CHANNEL_SPLIT", "1002")
    monkeypatch.setenv("CARD_ID_TOP_PARTNERS", "1003")
    monkeypatch.setenv("CARD_ID_MRR_TREND", "159")
    monkeypatch.setenv("CARD_ID_ARR_AT_RISK", "1006")
    monkeypatch.setenv("CARD_ID_UPSELL_OPPORTUNITIES", "1007")
    monkeypatch.setenv("CARD_ID_REVENUE_COMPARISON", "1008")
    monkeypatch.setenv("CARD_ID_DATA_QUALITY_SIGNALS", "1009")
    monkeypatch.setenv("CARD_ID_LICENSE_QUERY", "1010")

    # Bust caches.
    import connector.settings as s

    s._settings = None
    import importlib

    import connector.rpc_config as rc

    importlib.reload(rc)
    import connector.rpcs.partner_revenue as pr

    importlib.reload(pr)
    import connector.rpcs.channel_split as cs

    importlib.reload(cs)
    import connector.rpcs.top_partners as tp

    importlib.reload(tp)
    import connector.rpcs.mrr_trend as mt

    importlib.reload(mt)
    import connector.rpcs.arr_at_risk as ar

    importlib.reload(ar)
    import connector.rpcs.upsell_opportunities as up

    importlib.reload(up)
    import connector.rpcs.revenue_comparison as rev

    importlib.reload(rev)
    import connector.rpcs.data_quality_signals as dq

    importlib.reload(dq)
    import connector.rpcs.license_query as lq

    importlib.reload(lq)
    import connector.rpcs._registration as reg

    importlib.reload(reg)

    from connector.app import create_app

    app = create_app()

    captured: dict[str, Any] = {"calls": []}
    canned: dict[int, dict] = {}

    async def fake_execute_card(self, card_id, *, parameters=None, ignore_cache=True, timeout=None):
        captured["calls"].append({"card_id": card_id, "parameters": parameters})
        return canned.get(card_id, {"data": {"rows": [], "cols": []}})

    monkeypatch.setattr(MetabaseClient, "execute_card", fake_execute_card)
    # Stub Metabase client into app state since lifespan won't actually open it without a real key.
    app.state.metabase = MetabaseClient(base_url="http://stub", api_key="stub", timeout_seconds=5.0)

    tc = TestClient(app)
    tc.captured = captured  # type: ignore[attr-defined]
    tc.canned = canned  # type: ignore[attr-defined]
    return tc


HEADERS = {"X-Connector-API-Key": "test-key"}


def _stub_card(
    canned: dict[int, dict], card_id: int, rows: list[list], col_names: list[str]
) -> None:
    canned[card_id] = {"data": {"rows": rows, "cols": [{"name": n} for n in col_names]}}


def test_partner_revenue_envelope_and_reshape(client: TestClient) -> None:
    _stub_card(
        client.canned,
        1001,
        [["Partner A", "Parent A", "1234.56", 5, 3]],
        ["partner", "canonical_parent", "net_revenue", "line_count", "distinct_license_count"],
    )
    r = client.post(
        "/rpc/partner_revenue",
        headers=HEADERS,
        json={"start_date": "2026-01-01", "end_date": "2026-03-31"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["source_question_id"] == 1001
    assert body["meta"]["kind"] == "catalog"
    rows = body["data"]["rows"]
    assert rows[0]["partner"] == "Partner A"
    assert rows[0]["net_revenue"] == "1234.56"


def test_partner_revenue_validation_error_on_bad_dates(client: TestClient) -> None:
    r = client.post(
        "/rpc/partner_revenue",
        headers=HEADERS,
        json={"start_date": "2026-03-01", "end_date": "2026-01-01"},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_channel_split_groups_partner_direct_total(client: TestClient) -> None:
    _stub_card(
        client.canned,
        1002,
        [["1000.00", "500.00", 10, 5, 8, 3]],
        [
            "partner_revenue",
            "direct_revenue",
            "partner_lines",
            "direct_lines",
            "partner_distinct_licenses",
            "direct_distinct_licenses",
        ],
    )
    r = client.post(
        "/rpc/channel_split",
        headers=HEADERS,
        json={"start_date": "2026-01-01", "end_date": "2026-03-31"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["partner"]["revenue"] == "1000.00"
    assert data["direct"]["revenue"] == "500.00"
    assert data["total"]["revenue"] == "1500.00"
    assert data["total"]["line_count"] == 15


def test_top_partners_limit_bounds_enforced(client: TestClient) -> None:
    r = client.post(
        "/rpc/top_partners",
        headers=HEADERS,
        json={"start_date": "2026-01-01", "end_date": "2026-03-31", "limit": 0},
    )
    assert r.status_code == 422


def test_top_partners_happy_path(client: TestClient) -> None:
    _stub_card(
        client.canned,
        1003,
        [[1, "Partner A", "Parent A", "999.00"], [2, "Partner B", None, "888.00"]],
        ["rank", "partner", "canonical_parent", "net_revenue"],
    )
    r = client.post(
        "/rpc/top_partners",
        headers=HEADERS,
        json={"start_date": "2026-01-01", "end_date": "2026-03-31", "limit": 5},
    )
    assert r.status_code == 200
    rows = r.json()["data"]["rows"]
    assert [row["rank"] for row in rows] == [1, 2]
    assert rows[0]["net_revenue"] == "999.00"


def test_mrr_trend_groups_segments_per_month(client: TestClient) -> None:
    _stub_card(
        client.canned,
        159,
        [
            ["2026-01-01", "100.00", "Cloud", "Direct"],
            ["2026-01-01", "50.00", "DC", "Direct"],
            ["2026-02-01", "200.00", "Cloud", "Partner"],
        ],
        ["mrr_month", "mrr_contribution", "customer_type", "partner_type"],
    )
    r = client.post("/rpc/mrr_trend", headers=HEADERS, json={"months_back": 24})
    assert r.status_code == 200, r.text
    series = r.json()["data"]["series"]
    assert len(series) == 2
    jan = next(s for s in series if s["month"] == "2026-01-01")
    assert jan["mrr"] == "150.00"
    assert jan["by_customer_type"]["Cloud"] == "100.00"


def test_arr_at_risk_aggregates_total(client: TestClient) -> None:
    _stub_card(
        client.canned,
        1006,
        [["Partner A", "100.00", 3], ["Partner B", "50.00", 1]],
        ["key", "arr", "license_count"],
    )
    r = client.post("/rpc/arr_at_risk", headers=HEADERS, json={"group_by": "partner"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total_arr_at_risk"] == "150.00"
    assert len(data["breakdown"]) == 2


def test_upsell_opportunities_pricing_structure_coerced(client: TestClient) -> None:
    _stub_card(
        client.canned,
        1007,
        [["L1", "Partner A", "App X", 10, 25, "100.00", "250.00", "150.00", "cloud_marginal_band"]],
        [
            "license_id",
            "partner",
            "app",
            "current_seats",
            "projected_seats",
            "current_arr",
            "projected_arr",
            "delta_arr",
            "pricing_structure",
        ],
    )
    r = client.post(
        "/rpc/upsell_opportunities",
        headers=HEADERS,
        json={"horizon_days": 60, "min_seat_delta": 5},
    )
    assert r.status_code == 200, r.text
    rows = r.json()["data"]["rows"]
    assert rows[0]["pricing_structure"] == "cloud_marginal_band"
    assert rows[0]["delta_arr"] == "150.00"


def test_revenue_comparison_period_string_parsing(client: TestClient) -> None:
    _stub_card(
        client.canned,
        1008,
        [
            ["a", "Partner", "1000.00"],
            ["b", "Partner", "1200.00"],
            ["a", "Direct", "500.00"],
            ["b", "Direct", "400.00"],
        ],
        ["period", "dimension_key", "revenue"],
    )
    r = client.post(
        "/rpc/revenue_comparison",
        headers=HEADERS,
        json={"period_a": "Q1 2025", "period_b": "Q1 2026", "dimension": "channel"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["period_a"]["total"] == "1500.00"
    assert data["period_b"]["total"] == "1600.00"
    deltas = {d["key"]: d["delta"] for d in data["deltas"]}
    assert deltas["Partner"] == "200.00"
    assert deltas["Direct"] == "-100.00"


def test_revenue_comparison_invalid_period_string(client: TestClient) -> None:
    r = client.post(
        "/rpc/revenue_comparison",
        headers=HEADERS,
        json={"period_a": "garbage", "period_b": "Q1 2026"},
    )
    assert r.status_code == 422


def test_data_quality_signals_status_coerced(client: TestClient) -> None:
    _stub_card(
        client.canned,
        1009,
        [
            ["classification_drift", "OK", 12, "<25% drift"],
            ["refund_sign", "ACTION", 5, "expected 95% negative"],
        ],
        ["check_name", "status", "count_or_sample", "threshold_context"],
    )
    r = client.post("/rpc/data_quality_signals", headers=HEADERS, json={})
    assert r.status_code == 200, r.text
    checks = r.json()["data"]["checks"]
    assert {c["check_name"]: c["status"] for c in checks} == {
        "classification_drift": "OK",
        "refund_sign": "ACTION",
    }


def test_license_query_filter_params_only_sent_when_set(client: TestClient) -> None:
    _stub_card(
        client.canned,
        1010,
        [
            [
                "L1",
                "Partner A",
                "Acme",
                "Addon X",
                "active",
                "Cloud",
                "COMMERCIAL",
                "2025-01-01",
                "2026-01-01",
            ]
        ],
        [
            "id",
            "partner",
            "company",
            "addon",
            "status",
            "hosting",
            "license_type",
            "maintenance_start_date",
            "maintenance_end_date",
        ],
    )
    r = client.post(
        "/rpc/license_query",
        headers=HEADERS,
        json={"partner": "Partner A", "limit": 50},
    )
    assert r.status_code == 200, r.text
    rows = r.json()["data"]["rows"]
    assert rows[0]["id"] == "L1"
    assert rows[0]["maintenance_end_date"] == "2026-01-01"
    # Verify only the filters we set were sent (plus limit).
    last_call = client.captured["calls"][-1]
    param_names = {p["target"][1][1] for p in last_call["parameters"]}
    assert "partner" in param_names
    assert "limit" in param_names
    assert "company" not in param_names
    assert "hosting" not in param_names


def test_describe_catalog_lists_all_rpcs(client: TestClient) -> None:
    r = client.post("/rpc/describe_catalog", headers=HEADERS, json={})
    assert r.status_code == 200, r.text
    names = {e["name"] for e in r.json()["data"]["rpcs"]}
    assert names == {
        "describe_catalog",
        "partner_revenue",
        "channel_split",
        "top_partners",
        "mrr_trend",
        "arr_at_risk",
        "upsell_opportunities",
        "revenue_comparison",
        "data_quality_signals",
        "license_query",
        "execute_sql",
        "read_audit",
    }
    # execute_sql carries scope=raw_sql.
    raw = next(e for e in r.json()["data"]["rpcs"] if e["name"] == "execute_sql")
    assert raw["required_scope"] == "raw_sql"
