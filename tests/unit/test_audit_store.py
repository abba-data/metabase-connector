from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from connector.audit.models import AuditRecord, AuditStatus
from connector.audit.store import (
    InMemoryAuditStore,
    SQLiteAuditStore,
    build_store,
)
from connector.models import ConsumerType, Kind


def _record(
    *,
    timestamp: datetime,
    rpc_name: str,
    caller_id: str = "u1",
    status: AuditStatus = AuditStatus.SUCCESS,
    kind: Kind = Kind.CATALOG,
) -> AuditRecord:
    return AuditRecord(
        timestamp=timestamp,
        request_id=f"r-{timestamp.timestamp()}",
        caller_id=caller_id,
        consumer_type=ConsumerType.BACKEND_SERVICE_ACCOUNT,
        scope=["general"],
        rpc_name=rpc_name,
        rpc_version="1.0.0",
        parameters={"k": "v"},
        kind=kind,
        source_question_id=42 if kind == Kind.CATALOG else None,
        latency_ms=12,
        row_count=3,
        status=status,
        error_code=None if status == AuditStatus.SUCCESS else "FORBIDDEN",
        connector_version="0.1.0",
    )


@pytest.fixture(params=["memory", "sqlite"])
async def store(request, tmp_path: Path):
    if request.param == "memory":
        s = InMemoryAuditStore()
    else:
        s = SQLiteAuditStore(str(tmp_path / "audit.sqlite"))
    yield s
    await s.aclose()


async def test_write_then_query_round_trip(store) -> None:
    t = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    rec = _record(timestamp=t, rpc_name="partner_revenue")
    await store.write(rec)
    out = await store.query()
    assert len(out) == 1
    assert out[0].rpc_name == "partner_revenue"
    assert out[0].parameters == {"k": "v"}
    assert out[0].source_question_id == 42
    assert out[0].consumer_type == ConsumerType.BACKEND_SERVICE_ACCOUNT


async def test_query_filters_by_caller(store) -> None:
    t = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    await store.write(_record(timestamp=t, rpc_name="x", caller_id="alice"))
    await store.write(_record(timestamp=t, rpc_name="x", caller_id="bob"))
    rows = await store.query(caller_id="alice")
    assert [r.caller_id for r in rows] == ["alice"]


async def test_query_filters_by_rpc_and_status(store) -> None:
    t = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    await store.write(_record(timestamp=t, rpc_name="x", status=AuditStatus.SUCCESS))
    await store.write(_record(timestamp=t, rpc_name="y", status=AuditStatus.ERROR))
    rows = await store.query(rpc_name="y", status=AuditStatus.ERROR)
    assert len(rows) == 1
    assert rows[0].rpc_name == "y"
    assert rows[0].status == AuditStatus.ERROR


async def test_query_time_range(store) -> None:
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    await store.write(_record(timestamp=base, rpc_name="x"))
    await store.write(_record(timestamp=base + timedelta(hours=1), rpc_name="x"))
    await store.write(_record(timestamp=base + timedelta(days=1), rpc_name="x"))
    rows = await store.query(
        start_time=base + timedelta(minutes=30),
        end_time=base + timedelta(hours=2),
    )
    assert len(rows) == 1


async def test_query_orders_newest_first(store) -> None:
    base = datetime(2026, 5, 1, tzinfo=UTC)
    for i in range(3):
        await store.write(_record(timestamp=base + timedelta(hours=i), rpc_name=f"r{i}"))
    rows = await store.query()
    assert [r.rpc_name for r in rows] == ["r2", "r1", "r0"]


async def test_query_pagination(store) -> None:
    base = datetime(2026, 5, 1, tzinfo=UTC)
    for i in range(5):
        await store.write(_record(timestamp=base + timedelta(seconds=i), rpc_name=f"r{i}"))
    page1 = await store.query(limit=2, offset=0)
    page2 = await store.query(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {r.rpc_name for r in page1} & {r.rpc_name for r in page2} == set()


async def test_prune_older_than(store) -> None:
    now = datetime.now(UTC)
    await store.write(_record(timestamp=now - timedelta(days=400), rpc_name="old"))
    await store.write(_record(timestamp=now - timedelta(days=10), rpc_name="recent"))
    pruned = await store.prune_older_than(retention_days=365)
    assert pruned == 1
    rows = await store.query()
    assert [r.rpc_name for r in rows] == ["recent"]


def test_build_store_dispatches() -> None:
    assert isinstance(build_store("memory", sqlite_path=""), InMemoryAuditStore)
    assert isinstance(build_store("sqlite", sqlite_path=":memory:"), SQLiteAuditStore)
    with pytest.raises(ValueError):
        build_store("nope", sqlite_path="")
