"""Per-RPC contract tests: send a canned call, validate the response body
against the OpenAPI schema for that path. Catches the failure mode where
the runtime returns a shape divergent from what consumers were promised.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

HEADERS = {"X-Connector-API-Key": "k"}


def _rewrite_refs(node: Any) -> Any:
    """Rewrite every '#/components/schemas/X' ref to '#/$defs/X' recursively."""
    if isinstance(node, dict):
        return {
            k: (
                v.replace("#/components/schemas/", "#/$defs/")
                if k == "$ref" and isinstance(v, str)
                else _rewrite_refs(v)
            )
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_rewrite_refs(v) for v in node]
    return node


def _build_validator(openapi_doc: dict[str, Any], path: str, status: str = "200"):
    op = openapi_doc["paths"][path]["post"]
    response_schema = op["responses"][status]["content"]["application/json"]["schema"]
    components = openapi_doc.get("components", {}).get("schemas", {})

    full_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": _rewrite_refs(components),
        **_rewrite_refs(response_schema),
    }
    return Draft202012Validator(full_schema)


def _stub_card(canned: dict[int, dict], card_id: int, rows: list[list], cols: list[str]) -> None:
    canned[card_id] = {"data": {"rows": rows, "cols": [{"name": c} for c in cols]}}


def _validate_or_fail(validator: Draft202012Validator, body: Any, *, where: str) -> None:
    errors = list(validator.iter_errors(body))
    if errors:
        msgs = "\n  ".join(f"{list(e.path)}: {e.message}" for e in errors)
        raise AssertionError(f"{where}: response did not match schema:\n  {msgs}")


def test_describe_catalog_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    v = _build_validator(openapi_doc, "/rpc/describe_catalog")
    r = contract_client.post("/rpc/describe_catalog", headers=HEADERS, json={})
    assert r.status_code == 200, r.text
    _validate_or_fail(v, r.json(), where="describe_catalog")


def test_partner_revenue_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    _stub_card(
        contract_client.canned,
        1001,
        [["P", "Pp", "100.00", 5, 3]],
        ["partner", "canonical_parent", "net_revenue", "line_count", "distinct_license_count"],
    )
    v = _build_validator(openapi_doc, "/rpc/partner_revenue")
    r = contract_client.post(
        "/rpc/partner_revenue",
        headers=HEADERS,
        json={"start_date": "2026-01-01", "end_date": "2026-03-31"},
    )
    assert r.status_code == 200, r.text
    _validate_or_fail(v, r.json(), where="partner_revenue")


def test_channel_split_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    _stub_card(
        contract_client.canned,
        1002,
        [["100", "50", 1, 1, 1, 1]],
        [
            "partner_revenue",
            "direct_revenue",
            "partner_lines",
            "direct_lines",
            "partner_distinct_licenses",
            "direct_distinct_licenses",
        ],
    )
    v = _build_validator(openapi_doc, "/rpc/channel_split")
    r = contract_client.post(
        "/rpc/channel_split",
        headers=HEADERS,
        json={"start_date": "2026-01-01", "end_date": "2026-03-31"},
    )
    assert r.status_code == 200, r.text
    _validate_or_fail(v, r.json(), where="channel_split")


def test_top_partners_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    _stub_card(
        contract_client.canned,
        1003,
        [[1, "P", "Pp", "100"], [2, "Q", None, "50"]],
        ["rank", "partner", "canonical_parent", "net_revenue"],
    )
    v = _build_validator(openapi_doc, "/rpc/top_partners")
    r = contract_client.post(
        "/rpc/top_partners",
        headers=HEADERS,
        json={"start_date": "2026-01-01", "end_date": "2026-03-31", "limit": 5},
    )
    assert r.status_code == 200
    _validate_or_fail(v, r.json(), where="top_partners")


def test_mrr_trend_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    _stub_card(
        contract_client.canned,
        159,
        [["2026-01-01", "100", "Cloud", "Direct"]],
        ["mrr_month", "mrr_contribution", "customer_type", "partner_type"],
    )
    v = _build_validator(openapi_doc, "/rpc/mrr_trend")
    r = contract_client.post("/rpc/mrr_trend", headers=HEADERS, json={"months_back": 12})
    assert r.status_code == 200
    _validate_or_fail(v, r.json(), where="mrr_trend")


def test_arr_at_risk_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    _stub_card(
        contract_client.canned,
        1006,
        [["P", "100", 3]],
        ["key", "arr", "license_count"],
    )
    v = _build_validator(openapi_doc, "/rpc/arr_at_risk")
    r = contract_client.post("/rpc/arr_at_risk", headers=HEADERS, json={"horizon_days": 60, "group_by": "partner"})
    assert r.status_code == 200
    _validate_or_fail(v, r.json(), where="arr_at_risk")


def test_upsell_opportunities_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    _stub_card(
        contract_client.canned,
        1007,
        [["L1", "P", "App", 10, 25, "100", "250", "150", "cloud_marginal_band"]],
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
    v = _build_validator(openapi_doc, "/rpc/upsell_opportunities")
    r = contract_client.post(
        "/rpc/upsell_opportunities",
        headers=HEADERS,
        json={"horizon_days": 60, "min_seat_delta": 1},
    )
    assert r.status_code == 200
    _validate_or_fail(v, r.json(), where="upsell_opportunities")


def test_revenue_comparison_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    _stub_card(
        contract_client.canned,
        1008,
        [["a", "P", "100"], ["b", "P", "120"]],
        ["period", "dimension_key", "revenue"],
    )
    v = _build_validator(openapi_doc, "/rpc/revenue_comparison")
    r = contract_client.post(
        "/rpc/revenue_comparison",
        headers=HEADERS,
        json={"period_a": "Q1 2025", "period_b": "Q1 2026", "dimension": "partner"},
    )
    assert r.status_code == 200, r.text
    _validate_or_fail(v, r.json(), where="revenue_comparison")


def test_data_quality_signals_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    _stub_card(
        contract_client.canned,
        1009,
        [["check_a", "OK", 0, "<25%"]],
        ["check_name", "status", "count_or_sample", "threshold_context"],
    )
    v = _build_validator(openapi_doc, "/rpc/data_quality_signals")
    r = contract_client.post("/rpc/data_quality_signals", headers=HEADERS, json={})
    assert r.status_code == 200
    _validate_or_fail(v, r.json(), where="data_quality_signals")


def test_license_query_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    _stub_card(
        contract_client.canned,
        1010,
        [["L1", "P", "Acme", "Addon", "active", "Cloud", "COMMERCIAL", "2025-01-01", "2026-01-01"]],
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
    v = _build_validator(openapi_doc, "/rpc/license_query")
    r = contract_client.post("/rpc/license_query", headers=HEADERS, json={"limit": 10})
    assert r.status_code == 200
    _validate_or_fail(v, r.json(), where="license_query")


def test_execute_sql_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    v = _build_validator(openapi_doc, "/rpc/execute_sql")
    r = contract_client.post(
        "/rpc/execute_sql",
        headers=HEADERS,
        json={"database_id": 2, "sql": "SELECT 1"},
    )
    assert r.status_code == 200, r.text
    _validate_or_fail(v, r.json(), where="execute_sql")


def test_read_audit_response_matches_schema(contract_client: TestClient, openapi_doc: dict[str, Any]) -> None:
    v = _build_validator(openapi_doc, "/rpc/read_audit")
    r = contract_client.post("/rpc/read_audit", headers=HEADERS, json={"limit": 50})
    assert r.status_code == 200, r.text
    _validate_or_fail(v, r.json(), where="read_audit")


def test_validation_error_response_shape(contract_client: TestClient) -> None:
    """Error envelope from CRT-01C must be uniform across all RPCs."""
    r = contract_client.post(
        "/rpc/partner_revenue",
        headers=HEADERS,
        json={"start_date": "2026-03-01", "end_date": "2026-01-01"},
    )
    assert r.status_code == 422
    body = r.json()
    assert set(body.keys()) >= {"code", "message", "request_id"}
    assert body["code"] == "VALIDATION_ERROR"


def test_unauthorized_error_response_shape(contract_client: TestClient) -> None:
    r = contract_client.post("/rpc/describe_catalog", json={})
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == "UNAUTHORIZED"
    assert "request_id" in body
