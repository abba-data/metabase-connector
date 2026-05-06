"""Entrypoint per CLAUDE.md: run `python -m connector` to start the service.

Loads settings explicitly (no module-level state), constructs the app, and
hands off to uvicorn.
"""

from __future__ import annotations

import uvicorn

from connector.app import create_app
from connector.settings import load_settings


def main() -> None:
    settings = load_settings()
    app = create_app(settings=settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
