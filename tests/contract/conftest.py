from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from connector.audit.store import InMemoryAuditStore
from connector.clients.metabase import MetabaseClient


@pytest.fixture()
def contract_client(monkeypatch) -> TestClient:
    """Authed client + stubbed MetabaseClient with canned card responses.

    Wires every CARD_ID_* env so DESCRIPTOR.metabase_card_id is populated
    on every RPC; otherwise execute_card_rows raises METABASE_UNAVAILABLE
    before the contract surface is exercised.
    """
    monkeypatch.setenv(
        "CONNECTOR_API_KEYS",
        "k=u|interactive_script|general,raw_sql,operator",
    )
    monkeypatch.setenv("METABASE_API_KEY", "stub")
    card_envs = {
        "CARD_ID_PARTNER_REVENUE": "1001",
        "CARD_ID_CHANNEL_SPLIT": "1002",
        "CARD_ID_TOP_PARTNERS": "1003",
        "CARD_ID_MRR_TREND": "159",
        "CARD_ID_ARR_AT_RISK": "1006",
        "CARD_ID_UPSELL_OPPORTUNITIES": "1007",
        "CARD_ID_REVENUE_COMPARISON": "1008",
        "CARD_ID_DATA_QUALITY_SIGNALS": "1009",
        "CARD_ID_LICENSE_QUERY": "1010",
    }
    for k, v in card_envs.items():
        monkeypatch.setenv(k, v)

    import connector.settings as s

    s._settings = None

    import importlib

    import connector.rpc_config as rc

    importlib.reload(rc)

    for name in (
        "partner_revenue",
        "channel_split",
        "top_partners",
        "mrr_trend",
        "arr_at_risk",
        "upsell_opportunities",
        "revenue_comparison",
        "data_quality_signals",
        "license_query",
    ):
        importlib.reload(importlib.import_module(f"connector.rpcs.{name}"))
    importlib.reload(importlib.import_module("connector.rpcs._registration"))

    from connector.app import create_app

    app = create_app(audit_store=InMemoryAuditStore())

    canned: dict[int, dict[str, Any]] = {}

    async def fake_card(self, card_id, *, parameters=None, ignore_cache=True, timeout=None):
        return canned.get(card_id, {"data": {"rows": [], "cols": []}})

    async def fake_dataset(
        self, *, database_id, sql, parameters=None, template_tags=None, timeout=None
    ):
        return {
            "data": {"rows": [[1]], "cols": [{"name": "x", "base_type": "type/Integer"}]},
            "row_count": 1,
            "running_time": 1,
            "status": "completed",
        }

    monkeypatch.setattr(MetabaseClient, "execute_card", fake_card)
    monkeypatch.setattr(MetabaseClient, "execute_dataset", fake_dataset)

    app.state.metabase = MetabaseClient(base_url="http://stub", api_key="stub", timeout_seconds=5.0)

    tc = TestClient(app)
    tc.canned = canned  # type: ignore[attr-defined]
    return tc


@pytest.fixture()
def openapi_doc(contract_client: TestClient) -> dict[str, Any]:
    r = contract_client.get("/openapi.json")
    assert r.status_code == 200
    return r.json()
