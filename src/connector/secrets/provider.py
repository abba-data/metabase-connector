"""Secret provider abstraction per SEC-03B.

The same `SecretProvider` is consumed by:
  - the runtime (CRT-02A's MetabaseClient pulls METABASE_API_KEY)
  - the QAC-03 deploy pipeline (when implemented)

v1 ships an EnvVarSecretProvider. Production swap to AWS Secrets Manager,
HashiCorp Vault, or k8s Secrets is a config-only change once an alternate
implementation is plugged in.

Per spec contract:
  - Lazy fetch + cache: read at startup or first call.
  - Never log credential value.
  - Rotation: invalidate via .invalidate(name) without redeploy.
"""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Protocol

log = logging.getLogger("connector.secrets")


class SecretProvider(Protocol):
    def get(self, name: str) -> str: ...
    def invalidate(self, name: str) -> None: ...


class EnvVarSecretProvider:
    """v1 default. Reads `name` from the environment.

    Caches the value in-process so subsequent reads don't re-hit os.environ
    (mostly cosmetic — env reads are cheap — but matches the prod-shaped
    contract where fetches may be expensive).
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._lock = Lock()

    def get(self, name: str) -> str:
        with self._lock:
            cached = self._cache.get(name)
        if cached is not None:
            return cached
        value = os.environ.get(name, "")
        if not value:
            log.warning("SecretProvider.get(%r) returned empty value.", name)
        with self._lock:
            self._cache[name] = value
        return value

    def invalidate(self, name: str) -> None:
        with self._lock:
            self._cache.pop(name, None)


class StaticSecretProvider:
    """Tests + dev fixtures. Pre-loaded with a dict."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = dict(values)

    def get(self, name: str) -> str:
        return self._values.get(name, "")

    def invalidate(self, name: str) -> None:
        return None


def build_provider(kind: str = "env") -> SecretProvider:
    if kind == "env":
        return EnvVarSecretProvider()
    if kind == "static":
        return StaticSecretProvider({})
    # Future: 'aws_secrets_manager', 'vault', 'k8s_secret'.
    raise ValueError(f"Unknown secret provider: {kind!r}")
