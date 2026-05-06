from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from connector.audit.models import AuditRecord, AuditStatus
from connector.models import ConsumerType, Kind

log = logging.getLogger("connector.audit")


class AuditQuery(Protocol):
    start_time: datetime | None
    end_time: datetime | None
    caller_id: str | None
    rpc_name: str | None
    kind: Kind | None
    status: AuditStatus | None
    limit: int
    offset: int


class AuditStore(Protocol):
    async def write(self, record: AuditRecord) -> None: ...
    async def query(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        caller_id: str | None = None,
        rpc_name: str | None = None,
        kind: Kind | None = None,
        status: AuditStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditRecord]: ...
    async def prune_older_than(self, retention_days: int) -> int: ...
    async def aclose(self) -> None: ...


class InMemoryAuditStore:
    """Tests + ephemeral dev. Holds records in a list."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._lock = Lock()

    async def write(self, record: AuditRecord) -> None:
        with self._lock:
            self._records.append(record)

    async def query(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        caller_id: str | None = None,
        rpc_name: str | None = None,
        kind: Kind | None = None,
        status: AuditStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditRecord]:
        with self._lock:
            rows = list(self._records)
        rows = [
            r
            for r in rows
            if (start_time is None or r.timestamp >= start_time)
            and (end_time is None or r.timestamp <= end_time)
            and (caller_id is None or r.caller_id == caller_id)
            and (rpc_name is None or r.rpc_name == rpc_name)
            and (kind is None or r.kind == kind)
            and (status is None or r.status == status)
        ]
        rows.sort(key=lambda r: r.timestamp, reverse=True)
        return rows[offset : offset + limit]

    async def prune_older_than(self, retention_days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        with self._lock:
            before = len(self._records)
            self._records = [r for r in self._records if r.timestamp >= cutoff]
            return before - len(self._records)

    async def aclose(self) -> None:
        return None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    request_id TEXT NOT NULL,
    caller_id TEXT,
    consumer_type TEXT,
    scope TEXT,
    rpc_name TEXT,
    rpc_version TEXT,
    parameters TEXT,
    kind TEXT,
    source_question_id INTEGER,
    latency_ms INTEGER,
    row_count INTEGER,
    status TEXT NOT NULL,
    error_code TEXT,
    connector_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_caller ON audit_records(caller_id);
CREATE INDEX IF NOT EXISTS idx_audit_rpc ON audit_records(rpc_name);
"""


class SQLiteAuditStore:
    """v1 default audit storage. File-backed, append-only, time-bounded retention.

    Per spec SEC-02C: storage choice deferred. SQLite is the lightest viable v1
    that supports the operator-read endpoint and time-bounded deletion. Swap to
    Postgres or DataDog by implementing AuditStore against the same protocol.
    """

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    async def write(self, record: AuditRecord) -> None:
        row = (
            record.timestamp.isoformat(),
            record.request_id,
            record.caller_id,
            record.consumer_type.value if record.consumer_type else None,
            ",".join(record.scope) if record.scope else None,
            record.rpc_name,
            record.rpc_version,
            json.dumps(record.parameters) if record.parameters is not None else None,
            record.kind.value if record.kind else None,
            record.source_question_id,
            record.latency_ms,
            record.row_count,
            record.status.value,
            record.error_code,
            record.connector_version,
        )
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO audit_records (
                    timestamp, request_id, caller_id, consumer_type, scope,
                    rpc_name, rpc_version, parameters, kind, source_question_id,
                    latency_ms, row_count, status, error_code, connector_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

    async def query(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        caller_id: str | None = None,
        rpc_name: str | None = None,
        kind: Kind | None = None,
        status: AuditStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if start_time is not None:
            clauses.append("timestamp >= ?")
            params.append(start_time.isoformat())
        if end_time is not None:
            clauses.append("timestamp <= ?")
            params.append(end_time.isoformat())
        if caller_id is not None:
            clauses.append("caller_id = ?")
            params.append(caller_id)
        if rpc_name is not None:
            clauses.append("rpc_name = ?")
            params.append(rpc_name)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind.value)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        # `where` comes from a closed set of literal clauses above; values bind
        # via `?` placeholders, so this concat is safe by construction.
        select_cols = "timestamp, request_id, caller_id, consumer_type, scope, rpc_name, rpc_version, parameters, kind, source_question_id, latency_ms, row_count, status, error_code, connector_version"
        sql = f"SELECT {select_cols} FROM audit_records {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"  # noqa: S608
        params.extend([limit, offset])
        with self._lock:
            cursor = self._conn.execute(sql, params)
            raw_rows = cursor.fetchall()
        return [_row_to_record(r) for r in raw_rows]

    async def prune_older_than(self, retention_days: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        with self._lock:
            cursor = self._conn.execute("DELETE FROM audit_records WHERE timestamp < ?", (cutoff,))
            return cursor.rowcount or 0

    async def aclose(self) -> None:
        with self._lock:
            self._conn.close()


def _row_to_record(r: tuple[Any, ...]) -> AuditRecord:
    (
        ts,
        rid,
        caller,
        ctype,
        scope,
        rpc,
        ver,
        params_json,
        kind,
        sqid,
        lat,
        rc,
        status,
        err,
        cv,
    ) = r
    return AuditRecord(
        timestamp=datetime.fromisoformat(ts),
        request_id=rid,
        caller_id=caller,
        consumer_type=ConsumerType(ctype) if ctype else None,
        scope=scope.split(",") if scope else [],
        rpc_name=rpc,
        rpc_version=ver,
        parameters=json.loads(params_json) if params_json else None,
        kind=Kind(kind) if kind else None,
        source_question_id=sqid,
        latency_ms=lat,
        row_count=rc,
        status=AuditStatus(status),
        error_code=err,
        connector_version=cv,
    )


def build_store(kind: str, *, sqlite_path: str) -> AuditStore:
    if kind == "memory":
        return InMemoryAuditStore()
    if kind == "sqlite":
        return SQLiteAuditStore(sqlite_path)
    raise ValueError(f"Unknown audit store: {kind!r}. Use 'sqlite' or 'memory'.")
