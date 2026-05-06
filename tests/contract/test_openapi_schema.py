from __future__ import annotations

from typing import Any

import pytest


def test_openapi_doc_is_valid_openapi_3(openapi_doc: dict[str, Any]) -> None:
    assert openapi_doc["openapi"].startswith("3.")
    assert openapi_doc["info"]["title"] == "Modus Data Connector"
    paths = openapi_doc["paths"]
    expected = {
        "/healthz",
        "/healthz/upstream",
        "/rpc/describe_catalog",
        "/rpc/partner_revenue",
        "/rpc/channel_split",
        "/rpc/top_partners",
        "/rpc/mrr_trend",
        "/rpc/arr_at_risk",
        "/rpc/upsell_opportunities",
        "/rpc/revenue_comparison",
        "/rpc/data_quality_signals",
        "/rpc/license_query",
        "/rpc/execute_sql",
        "/rpc/read_audit",
    }
    assert expected.issubset(paths.keys()), f"missing: {expected - paths.keys()}"


@pytest.mark.parametrize(
    "rpc_name",
    [
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
    ],
)
def test_every_rpc_response_includes_meta_envelope(openapi_doc: dict[str, Any], rpc_name: str) -> None:
    """Every RPC's 200 response must be Response[T] with required meta fields."""
    path = f"/rpc/{rpc_name}"
    op = openapi_doc["paths"][path]["post"]
    schema_ref = op["responses"]["200"]["content"]["application/json"]["schema"]

    # Resolve $ref to component schemas.
    components = openapi_doc.get("components", {}).get("schemas", {})
    resolved = _resolve(schema_ref, components)
    properties = resolved.get("properties", {})
    assert "data" in properties, f"{rpc_name}: response missing 'data'"
    assert "meta" in properties, f"{rpc_name}: response missing 'meta'"

    meta_schema = _resolve(properties["meta"], components)
    meta_props = meta_schema.get("properties", {})
    required_meta = {"freshness_window_days", "kind", "request_id"}
    assert required_meta.issubset(meta_props.keys()), (
        f"{rpc_name}: meta missing fields {required_meta - meta_props.keys()}"
    )


def test_security_scheme_declared(openapi_doc: dict[str, Any]) -> None:
    schemes = openapi_doc.get("components", {}).get("securitySchemes", {})
    assert "ConnectorApiKey" in schemes, "ConnectorApiKey security scheme missing"
    api_key = schemes["ConnectorApiKey"]
    assert api_key["type"] == "apiKey"
    assert api_key["in"] == "header"
    assert api_key["name"] == "X-Connector-API-Key"


def test_every_rpc_route_requires_api_key(openapi_doc: dict[str, Any]) -> None:
    """Every /rpc/* path must declare ConnectorApiKey security."""
    for path, item in openapi_doc["paths"].items():
        if not path.startswith("/rpc/"):
            continue
        for method, op in item.items():
            if method.lower() != "post":
                continue
            security = op.get("security") or []
            assert any("ConnectorApiKey" in s for s in security), (
                f"{method.upper()} {path}: missing ConnectorApiKey in security"
            )


def _resolve(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        ref = schema["$ref"]
        # "#/components/schemas/Foo"
        name = ref.split("/")[-1]
        return _resolve(components[name], components)
    return schema
