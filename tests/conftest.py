from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("METABASE_URL", "http://metabase.test")
os.environ.setdefault("METABASE_API_KEY", "")
os.environ.setdefault("CONNECTOR_API_KEYS", "")
os.environ["AUDIT_STORE"] = "memory"


@pytest.fixture()
def client() -> TestClient:
    from connector.app import create_app

    app = create_app()
    return TestClient(app)
