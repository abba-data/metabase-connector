# CLAUDE.md — FastAPI Project Guidelines

## Project Overview

This is a FastAPI-based Python API project. All code must be strictly typed, fully tested, and production-ready. The stack enforces zero global state, strict control flow, and deterministic configuration loading.

---

## Tooling & Runtime

- **Package manager**: `uv` (all dependency operations use `uv add`, `uv remove`, `uv sync`, `uv run`)
- **Python version**: 3.12+ (specified in `pyproject.toml`)
- **Type checker**: `basedpyright` in strict mode
- **Linter & formatter**: `ruff` (linting AND formatting — no black, no isort, no flake8)
- **Test runner**: `pytest` with `anyio` backend for async test support
- **Framework**: FastAPI with Uvicorn

### Key Commands

```bash
uv sync                          # Install/sync all dependencies
uv run basedpyright              # Type-check the entire project
uv run ruff check .              # Lint
uv run ruff format .             # Format
uv run ruff check --fix .        # Lint with auto-fix
uv run pytest                    # Run all tests
uv run pytest -x                 # Stop on first failure
uv run pytest -k "test_name"     # Run specific test
uv run pytest --cov=app          # Run with coverage
```

---

## Architecture Rules

### NO Global State — Zero Exceptions

This is the single most important rule in the codebase. Violating it is always wrong.

- **NEVER** define mutable variables at module level. No global dicts, lists, singletons, caches, or registries.
- **NEVER** use module-level code that performs I/O, reads env vars, opens connections, or has side effects.
- **NEVER** instantiate clients, loggers with runtime config, DB engines, or HTTP sessions at import time.
- **NEVER** write bare logic at module scope — every statement must live inside a `def`, `async def`, or `class` body.
- The **only** permitted module-level content is: imports, type aliases, constants (`Final`), dataclass/model class definitions, pure function definitions, and `TYPE_CHECKING` blocks.
- If a framework pattern (e.g., FastAPI's `app = FastAPI()`) forces a module-level object, isolate it in a single factory function and call that factory from the entrypoint. The object must not be constructed as a side effect of importing the module.

```python
# WRONG — globally scoped, import-time side effects
app = FastAPI()
settings = Settings()
logger = setup_logger()
redis = Redis(host=settings.REDIS_HOST)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

# CORRECT — factory function, explicit wiring
def create_app() -> FastAPI:
    settings = load_settings()
    logger = setup_logger(settings)
    app = FastAPI(title=settings.app_name, lifespan=_lifespan)
    # mount routes, middleware, etc.
    return app
```

### Strict Control Flow

- Every code path must be explicitly handled. No fallthrough logic.
- All functions must have a single, clear return type. Never rely on implicit `None` returns.
- Use early returns for guard clauses.
- Prefer exhaustive `match` statements over `if/elif` chains when branching on enums or literals. Always include a default branch that raises.
- Never use bare `except:`. Always catch specific exception types.

---

## Type System — basedpyright Strict Mode

All code must pass `basedpyright` in strict mode with zero errors. This is non-negotiable.

### Configuration (`pyproject.toml`)

```toml
[tool.basedpyright]
typeCheckingMode = "strict"
pythonVersion = "3.12"
reportMissingTypeStubs = false
reportUnusedImport = false          # ruff handles this
```

### Typing Rules

- **Every** function signature must have full parameter and return type annotations. No exceptions.
- Use `T | None` union syntax, never `Optional[T]`.
- Use builtin generics: `list[str]`, `dict[str, int]`, `tuple[int, ...]` — never `List`, `Dict`, `Tuple` from `typing`.
- Annotate all class attributes, instance variables, and local variables where the type is not obvious from assignment.
- Use `TypeVar`, `ParamSpec`, `Protocol`, and `TypeAlias` from `typing` where needed.
- Prefer `Sequence[T]` / `Mapping[K, V]` in function parameters over concrete `list` / `dict` when mutation is not required.
- For callables, use `Callable[[ArgTypes], ReturnType]` or `Protocol` with `__call__`.
- All Pydantic models count as typed — field types are mandatory.
- Never use `Any` unless absolutely unavoidable (e.g., wrapping an untyped third-party lib). Add a `# pyright: ignore[reportAny]` comment with justification if forced.
- Never use `type: ignore` without a specific error code.

---

## Configuration — Pydantic Settings

Configuration is managed via `pydantic_settings.BaseSettings` and is **never loaded at module scope**.

### Environment-Based Loading

```python
from enum import StrEnum
from functools import lru_cache
from typing import Final

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = Environment.LOCAL
    app_name: str = "my-api"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Secrets — use SecretStr so values never leak in logs/repr
    database_url: SecretStr = Field(...)
    api_key: SecretStr = Field(...)

    # Datadog
    dd_api_key: SecretStr | None = None
    dd_service: str = "my-api"
    dd_env: str = "local"


def load_settings() -> AppSettings:
    """Load settings from environment. Call this inside factory functions, never at module level."""
    return AppSettings()  # type: ignore[call-arg]  # env vars fill required fields
```

- The `ENV` or `APP_ENV` variable selects the environment (`local`, `staging`, `production`).
- Never read `os.environ` directly anywhere in application code. Always go through the settings object.
- Pass the settings object explicitly via dependency injection — never stash it in a global.

---

## FastAPI Application Structure

### App Factory Pattern

```python
# app/main.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import AppSettings, load_settings
from app.logging import setup_logging
from app.middleware import register_middleware
from app.routes import register_routes


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup: initialize resources, attach to app.state
    settings: AppSettings = app.state.settings
    setup_logging(settings)
    # ... open DB pools, warm caches, etc.
    yield
    # Shutdown: close resources
    # ... close DB pools, flush logs, etc.


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = settings
    register_middleware(app, settings)
    register_routes(app)
    return app
```

```python
# app/__main__.py  (entrypoint)
import uvicorn

from app.config import load_settings
from app.main import create_app


def main() -> None:
    settings = load_settings()
    app = create_app()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
```

### Dependency Injection

- Use FastAPI's `Depends()` system to inject settings, DB sessions, loggers, and services into route handlers.
- Never import and use a module-level settings instance inside a handler.

```python
from fastapi import Depends, Request

from app.config import AppSettings


def get_settings(request: Request) -> AppSettings:
    settings: AppSettings = request.app.state.settings
    return settings


async def some_handler(settings: AppSettings = Depends(get_settings)) -> dict[str, str]:
    return {"app": settings.app_name}
```

---

## Rate Limiting — SlowAPI

Use `slowapi` for rate limiting. Attach the limiter in the app factory, never at module level.

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


def register_middleware(app: FastAPI, settings: AppSettings) -> None:
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    # ... other middleware
```

Apply limits on individual routes using the limiter from `request.app.state`:

```python
from slowapi import Limiter


@router.get("/resource")
@limiter.limit("10/minute")
async def get_resource(request: Request) -> dict[str, str]:
    ...
```

---

## Logging — Loguru with JSON/Text Modes

Loguru is the logging backend. Configuration is **environment-dependent** and set up inside the lifespan/factory — never at module scope.

### Setup

```python
# app/logging.py
import sys

import loguru
from loguru import logger

from app.config import AppSettings, Environment


def setup_logging(settings: AppSettings) -> None:
    """Configure loguru. Must be called once during app startup, never at import time."""
    logger.remove()  # Remove default handler

    if settings.env == Environment.LOCAL:
        # Human-readable, colorized output for local dev
        logger.add(
            sys.stderr,
            level="DEBUG",
            format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
            colorize=True,
        )
    else:
        # JSON structured logs for staging/production — ingested by Datadog
        logger.add(
            sys.stderr,
            level="INFO",
            format="{message}",
            serialize=True,  # outputs JSON
        )
```

### Logging Rules

- Import `from loguru import logger` wherever needed — loguru's `logger` is a lazy singleton that respects the runtime configuration set via `setup_logging`. This is the one accepted quasi-global in the project because loguru is designed this way and there is no DI alternative. **No other global is acceptable.**
- Always use structured logging: `logger.info("event description", user_id=uid, action="create")`.
- Never log secrets, tokens, passwords, or full request bodies containing PII.
- Use appropriate levels: `debug` for dev tracing, `info` for business events, `warning` for recoverable issues, `error` for failures, `critical` for fatal conditions.

---

## Observability — Datadog (APM, Logs, Error Tracking)

Datadog integration is done via `ddtrace`. It is initialized during app startup, never at module level.

### Setup

```python
# app/observability.py
from app.config import AppSettings, Environment


def setup_datadog(settings: AppSettings) -> None:
    """Initialize Datadog tracing and log correlation. Call during app startup only."""
    if settings.env == Environment.LOCAL:
        return  # No Datadog in local dev

    import ddtrace
    from ddtrace import config as dd_config, patch_all

    dd_config.env = settings.dd_env
    dd_config.service = settings.dd_service
    patch_all()  # Auto-instrument FastAPI, httpx, SQLAlchemy, etc.
```

### Rules

- Call `setup_datadog(settings)` at the top of the lifespan, **before** any other initialization (so all subsequent I/O is traced).
- `ddtrace` auto-instruments FastAPI, `httpx`, `asyncpg`, `sqlalchemy`, `redis`, and others — no manual span creation needed for standard operations.
- For custom spans: use `ddtrace.tracer.trace("operation.name")` context manager inside functions, never at module level.
- Loguru's JSON output is auto-correlated by the Datadog agent when `DD_LOGS_INJECTION=true` is set.
- For error tracking, unhandled exceptions propagate through FastAPI's exception handlers and are captured by `ddtrace`. Add a global exception handler that logs and re-raises.

---

## Testing — pytest + anyio

### Configuration (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
filterwarnings = ["error"]
```

Install `pytest-asyncio` or `anyio` with the pytest plugin for async test support.

### Testing Rules

- **Every** public function and endpoint must have tests. No exceptions.
- Use `pytest` fixtures for setup/teardown. Never use module-level test state.
- Async tests use `async def test_...` — the `asyncio_mode = "auto"` setting handles the event loop.
- Use `httpx.AsyncClient` with FastAPI's `ASGITransport` for integration tests — not `TestClient` (which is sync).
- Isolate all external dependencies with mocks or fakes. Tests must not make real HTTP calls, DB queries, or file I/O.
- Use factories (via `factory_boy` or plain functions) for test data — never hardcode deeply nested dicts.
- Each test file mirrors the source file: `app/services/users.py` → `tests/services/test_users.py`.

### Async Integration Test Pattern

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client() -> AsyncClient:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

### Fixtures

- Prefer `function`-scoped fixtures (the default). Use `session` scope only for truly expensive, read-only resources.
- Fixtures that produce async resources must use `@pytest.fixture` with `async def` and `yield`.
- Never use `autouse=True` unless the fixture is genuinely needed by every test in the module.

---

## Ruff Configuration

```toml
[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "N",      # pep8-naming
    "UP",     # pyupgrade
    "B",      # flake8-bugbear
    "A",      # flake8-builtins
    "SIM",    # flake8-simplify
    "RUF",    # ruff-specific rules
    "ANN",    # flake8-annotations (enforce type annotations)
    "ASYNC",  # flake8-async
    "S",      # flake8-bandit (security)
    "T20",    # flake8-print (no print statements)
    "PTH",    # flake8-use-pathlib
    "RET",    # flake8-return
    "TCH",    # flake8-type-checking
    "ARG",    # flake8-unused-arguments
]
ignore = [
    "ANN101",  # missing type annotation for self
    "ANN102",  # missing type annotation for cls
]

[tool.ruff.lint.isort]
known-first-party = ["app"]
```

---

## Project Layout

```
.
├── pyproject.toml
├── uv.lock
├── CLAUDE.md
├── .env.example
├── app/
│   ├── __init__.py
│   ├── __main__.py          # Entrypoint: calls create_app + uvicorn
│   ├── main.py              # App factory (create_app) + lifespan
│   ├── config.py            # Pydantic settings + load_settings()
│   ├── logging.py           # Loguru setup
│   ├── observability.py     # Datadog setup
│   ├── middleware.py         # SlowAPI + other middleware registration
│   ├── dependencies.py      # Shared FastAPI Depends() functions
│   ├── exceptions.py        # Custom exception classes + handlers
│   ├── routes/
│   │   ├── __init__.py      # register_routes() aggregator
│   │   ├── health.py
│   │   └── ...
│   ├── services/            # Business logic (no FastAPI imports)
│   ├── repositories/        # Data access layer
│   ├── models/              # Pydantic request/response models
│   │   ├── __init__.py
│   │   └── ...
│   └── schemas/             # DB schemas (SQLAlchemy, etc.)
└── tests/
    ├── conftest.py           # Shared fixtures
    ├── routes/
    │   └── test_health.py
    ├── services/
    └── ...
```

---

## Code Style Reminders

- Imports are sorted by `ruff` (isort rules). Never manually reorder.
- No `print()` statements anywhere — use `logger` from loguru.
- No `assert` in production code — use explicit `if` + `raise`.
- String formatting: use f-strings. Never `%` or `.format()`.
- Use `pathlib.Path`, never `os.path`.
- Prefer `httpx` over `requests` for HTTP clients (async-native).
- All datetime objects must be timezone-aware. Use `datetime.datetime.now(datetime.UTC)`.
- Use `Final` for constants: `MAX_RETRIES: Final = 3`.
- Docstrings on all public functions and classes (Google style).

---

## Pre-Commit / CI Checklist

Before every commit, the following must all pass with zero errors:

```bash
uv run ruff format --check .     # Formatting
uv run ruff check .              # Linting
uv run basedpyright              # Type checking
uv run pytest                    # Tests
```

All four are enforced in CI. A failure in any one blocks the merge.