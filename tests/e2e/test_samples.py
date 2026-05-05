"""End-to-end sample tests.

Each test boots the connector in-process on a free port (uvicorn worker
thread), stubs Metabase responses, and runs the sample script as a
subprocess against the live connector. Catches the failure mode where
docs/samples drift from runtime.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn

from connector.app import create_app
from connector.audit.store import InMemoryAuditStore
from connector.clients.metabase import MetabaseClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLES = REPO_ROOT / "samples"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _ServerThread(threading.Thread):
    def __init__(self, app, port: int) -> None:
        super().__init__(daemon=True)
        self._config = uvicorn.Config(
            app=app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"
        )
        self._server = uvicorn.Server(self._config)

    def run(self) -> None:
        self._server.run()

    def stop(self) -> None:
        self._server.should_exit = True


def _wait_ready(url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"server did not become ready within {timeout}s")


def _stub_metabase_card(monkeypatch, canned: dict[int, dict]) -> None:
    async def fake_card(self, card_id, *, parameters=None, ignore_cache=True, timeout=None):
        return canned.get(card_id, {"data": {"rows": [], "cols": []}})

    monkeypatch.setattr(MetabaseClient, "execute_card", fake_card)


@pytest.fixture()
def live_connector(monkeypatch) -> Iterator[tuple[str, str]]:
    """Boot a real uvicorn process in a thread, return (base_url, api_key)."""
    monkeypatch.setenv(
        "CONNECTOR_API_KEYS",
        "e2e-key=e2e|backend_service_account|general,raw_sql,operator",
    )
    monkeypatch.setenv("METABASE_API_KEY", "stub")
    monkeypatch.setenv("CARD_ID_PARTNER_REVENUE", "1001")
    monkeypatch.setenv("CARD_ID_CHANNEL_SPLIT", "1002")
    monkeypatch.setenv("CARD_ID_ARR_AT_RISK", "1006")
    import connector.settings as s

    s._settings = None

    canned: dict[int, dict] = {
        1001: {
            "data": {
                "rows": [["Acme", "Acme Inc", "999.50", 4, 2]],
                "cols": [
                    {"name": "partner"},
                    {"name": "canonical_parent"},
                    {"name": "net_revenue"},
                    {"name": "line_count"},
                    {"name": "distinct_license_count"},
                ],
            }
        },
        1002: {
            "data": {
                "rows": [["1000", "500", 10, 5, 8, 3]],
                "cols": [
                    {"name": "partner_revenue"},
                    {"name": "direct_revenue"},
                    {"name": "partner_lines"},
                    {"name": "direct_lines"},
                    {"name": "partner_distinct_licenses"},
                    {"name": "direct_distinct_licenses"},
                ],
            }
        },
        1006: {
            "data": {
                "rows": [["overall", "1234.56", 9]],
                "cols": [{"name": "key"}, {"name": "arr"}, {"name": "license_count"}],
            }
        },
    }
    _stub_metabase_card(monkeypatch, canned)

    # Reload RPC modules so they pick up the new card-id env.
    import importlib

    import connector.rpc_config as rc

    importlib.reload(rc)
    for name in ("partner_revenue", "channel_split", "arr_at_risk"):
        importlib.reload(importlib.import_module(f"connector.rpcs.{name}"))
    importlib.reload(importlib.import_module("connector.rpcs._registration"))

    app = create_app(audit_store=InMemoryAuditStore())
    app.state.metabase = MetabaseClient(base_url="http://stub", api_key="stub", timeout_seconds=5.0)

    port = _free_port()
    server = _ServerThread(app, port)
    server.start()
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_ready(f"{base}/healthz")
        yield base, "e2e-key"
    finally:
        server.stop()
        server.join(timeout=5.0)


def _run_sample(script: Path, env_extra: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_extra, "PYTHONPATH": str(REPO_ROOT / "src")}
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


def test_backend_partner_revenue_job(live_connector, tmp_path: Path) -> None:
    base, api_key = live_connector
    out_path = tmp_path / "result.json"
    proc = _run_sample(
        SAMPLES / "backend" / "partner_revenue_job.py",
        {"CONNECTOR_URL": base, "CONNECTOR_API_KEY": api_key},
        str(out_path),
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out_path.read_text())
    assert data["meta"]["source_question_id"] == 1001
    assert data["data"]["rows"][0]["partner"] == "Acme"


def test_script_explore(live_connector) -> None:
    base, api_key = live_connector
    proc = _run_sample(
        SAMPLES / "script" / "explore.py",
        {"CONNECTOR_URL": base, "CONNECTOR_API_KEY": api_key},
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "=== Catalog ===" in out
    assert "describe_catalog" in out
    assert "channel_split" in out
    assert "=== arr_at_risk" in out


def test_llm_tools_builds_anthropic_definitions(live_connector) -> None:
    """The LLM sample exposes build_tools() — call it directly via subprocess
    so we exercise the same env-var loading path."""
    base, api_key = live_connector
    proc = _run_sample(
        SAMPLES / "llm" / "tools.py",
        {"CONNECTOR_URL": base, "CONNECTOR_API_KEY": api_key},
    )
    assert proc.returncode == 0, proc.stderr
    # tools.py prints the first 2000 chars of the JSON-encoded tool list.
    out = proc.stdout.strip()
    assert out.startswith("[")
    # Operator-scope RPC must be filtered out.
    assert "read_audit" not in out
