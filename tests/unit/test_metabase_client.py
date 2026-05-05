from __future__ import annotations

import httpx
import pytest
import respx

from connector.clients.metabase import MetabaseClient
from connector.errors import (
    ExceededSyncWindowError,
    MetabaseError,
    MetabaseTimeoutError,
    MetabaseUnavailableError,
)


@pytest.fixture()
async def mb() -> MetabaseClient:
    client = MetabaseClient(
        base_url="http://metabase.test", api_key="test-key", timeout_seconds=5.0
    )
    yield client
    await client.aclose()


@respx.mock
async def test_execute_card_success(mb: MetabaseClient) -> None:
    payload = {
        "data": {
            "rows": [[1, 2], [3, 4]],
            "cols": [{"name": "a"}, {"name": "b"}],
        }
    }
    route = respx.post("http://metabase.test/api/card/42/query").mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = await mb.execute_card(42, parameters=[{"type": "category", "value": "x"}])
    assert out == payload
    assert route.called
    assert route.calls.last.request.headers["X-API-Key"] == "test-key"
    body = route.calls.last.request.read()
    assert b"ignore_cache" in body
    assert b"parameters" in body


@respx.mock
async def test_execute_card_202_with_empty_body_raises_exceeded(mb: MetabaseClient) -> None:
    respx.post("http://metabase.test/api/card/42/query").mock(
        return_value=httpx.Response(202, json={})
    )
    with pytest.raises(ExceededSyncWindowError):
        await mb.execute_card(42)


@respx.mock
async def test_execute_card_202_with_completed_body_is_success(mb: MetabaseClient) -> None:
    """Some Metabase versions return 202 with the full data inline. Don't error on those."""
    payload = {
        "data": {"rows": [[1]], "cols": [{"name": "ping"}]},
        "row_count": 1,
        "running_time": 11,
        "status": "completed",
    }
    respx.post("http://metabase.test/api/card/42/query").mock(
        return_value=httpx.Response(202, json=payload)
    )
    out = await mb.execute_card(42)
    assert out == payload


@respx.mock
async def test_execute_card_5xx_raises_unavailable(mb: MetabaseClient) -> None:
    respx.post("http://metabase.test/api/card/42/query").mock(
        return_value=httpx.Response(503, text="upstream down")
    )
    with pytest.raises(MetabaseUnavailableError):
        await mb.execute_card(42)


@respx.mock
async def test_execute_card_4xx_raises_metabase_error(mb: MetabaseClient) -> None:
    respx.post("http://metabase.test/api/card/42/query").mock(
        return_value=httpx.Response(400, text="bad params")
    )
    with pytest.raises(MetabaseError):
        await mb.execute_card(42)


@respx.mock
async def test_execute_card_timeout_raises_metabase_timeout(mb: MetabaseClient) -> None:
    respx.post("http://metabase.test/api/card/42/query").mock(
        side_effect=httpx.TimeoutException("slow")
    )
    with pytest.raises(MetabaseTimeoutError):
        await mb.execute_card(42)


@respx.mock
async def test_execute_dataset_success(mb: MetabaseClient) -> None:
    payload = {"data": {"rows": []}}
    route = respx.post("http://metabase.test/api/dataset").mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = await mb.execute_dataset(database_id=2, sql="SELECT 1")
    assert out == payload
    assert route.called
    body = route.calls.last.request.read()
    assert b"native" in body and b"SELECT 1" in body
