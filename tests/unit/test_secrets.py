from __future__ import annotations

import pytest

from connector.secrets import (
    EnvVarSecretProvider,
    StaticSecretProvider,
    build_provider,
)


def test_env_var_provider_reads_and_caches(monkeypatch) -> None:
    monkeypatch.setenv("MY_KEY", "value-1")
    p = EnvVarSecretProvider()
    assert p.get("MY_KEY") == "value-1"

    # Cache hit even after env mutates.
    monkeypatch.setenv("MY_KEY", "value-2")
    assert p.get("MY_KEY") == "value-1"

    # Invalidate forces re-read.
    p.invalidate("MY_KEY")
    assert p.get("MY_KEY") == "value-2"


def test_env_var_provider_returns_empty_for_missing(monkeypatch) -> None:
    monkeypatch.delenv("MISSING", raising=False)
    p = EnvVarSecretProvider()
    assert p.get("MISSING") == ""


def test_static_provider_round_trip() -> None:
    p = StaticSecretProvider({"a": "1", "b": "2"})
    assert p.get("a") == "1"
    assert p.get("b") == "2"
    assert p.get("missing") == ""


def test_build_provider_dispatches() -> None:
    assert isinstance(build_provider("env"), EnvVarSecretProvider)
    assert isinstance(build_provider("static"), StaticSecretProvider)
    with pytest.raises(ValueError):
        build_provider("nonsense")
