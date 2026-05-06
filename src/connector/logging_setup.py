"""Loguru configuration. Per CLAUDE.md: must be called once during app
startup via setup_logging(); never at import time.

Local: human-readable colorized stderr.
Staging/production: JSON-serialized structured logs (Datadog ingests them).
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from connector.settings import AppSettings


def setup_logging(settings: AppSettings) -> None:
    from connector.settings import Environment

    logger.remove()
    if settings.env == Environment.LOCAL:
        logger.add(
            sys.stderr,
            level=settings.log_level,
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level:<8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
                "<level>{message}</level>"
            ),
            colorize=True,
        )
    else:
        logger.add(
            sys.stderr,
            level=settings.log_level,
            format="{message}",
            serialize=True,
        )
