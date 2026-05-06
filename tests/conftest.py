from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Environment defaults for tests — applied before any test module imports the app.
os.environ.setdefault("APP_METABASE_URL", "http://metabase.test")
os.environ.setdefault("APP_METABASE_API_KEY", "")
os.environ.setdefault("APP_CONNECTOR_API_KEYS", "")
os.environ["APP_AUDIT_STORE"] = "memory"
os.environ.setdefault("APP_ENV", "local")


@pytest.fixture(autouse=True)
def _bust_settings_cache() -> None:
    """Tests mutate env via monkeypatch; clear lru_cache so each test sees its own settings."""
    from connector.settings import load_settings

    load_settings.cache_clear()


@pytest.fixture()
def client() -> TestClient:
    from connector.app import create_app

    app = create_app()
    return TestClient(app)
