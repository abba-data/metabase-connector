"""Datadog APM/tracing setup. Per CLAUDE.md: called once at the top of
the lifespan, never at module level. No-op in LOCAL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connector.settings import AppSettings


def setup_datadog(settings: AppSettings) -> None:
    from connector.settings import Environment

    if settings.env == Environment.LOCAL:
        return

    # ddtrace is imported lazily so local dev has no import-time cost.
    from ddtrace import config as dd_config
    from ddtrace import patch_all

    dd_config.env = settings.dd_env
    dd_config.service = settings.dd_service
    patch_all()  # auto-instruments fastapi, httpx, sqlite3, etc.
