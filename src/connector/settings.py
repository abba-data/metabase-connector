from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    """Pydantic-loaded settings.

    Per CLAUDE.md: no module-level instantiation. Always go through
    `load_settings()` (cached via lru_cache) inside factory functions.
    Never read os.environ directly elsewhere in application code.
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = Environment.LOCAL
    app_name: str = "Modus Data Connector"
    debug: bool = False
    host: str = "0.0.0.0"  # noqa: S104  intentional bind-all in dev
    port: int = 8000
    log_level: str = "INFO"

    # Metabase
    metabase_url: str = "https://analytics.atlasauthority.com"
    metabase_api_key: SecretStr = Field(default=SecretStr(""))
    metabase_timeout_seconds: float = 30.0
    metabase_version_pin: str = ""

    # Connector consumer auth — `key=id|consumer_type|scopes[|rate_limit_class]`,
    # entries separated by `;` or newline.
    connector_api_keys: SecretStr = Field(default=SecretStr(""))

    default_freshness_window_days: int = 60

    # Audit
    audit_store: str = "sqlite"
    audit_db_path: str = "./data/audit.sqlite"
    audit_retention_days: int = 365

    # Rate limiting (slowapi-compatible strings; empty disables)
    rate_limit_default: str = "60/minute"
    rate_limit_raw_sql: str = "30/minute"
    rate_limit_operator: str = "120/minute"

    # Card IDs (None disables that RPC for upstream calls)
    card_id_partner_revenue: int | None = None
    card_id_channel_split: int | None = None
    card_id_top_partners: int | None = None
    card_id_mrr_trend: int | None = 159
    card_id_arr_at_risk: int | None = None
    card_id_upsell_opportunities: int | None = None
    card_id_revenue_comparison: int | None = None
    card_id_data_quality_signals: int | None = None
    card_id_license_query: int | None = None

    # Datadog
    dd_service: str = "metabase-connector"
    dd_env: str = "local"


@lru_cache(maxsize=1)
def load_settings() -> AppSettings:
    """Load settings from environment. Cached for the process lifetime;
    call `load_settings.cache_clear()` between tests that mutate env."""
    return AppSettings()


# Backwards-compat shim. Prefer load_settings() in new code.
def get_settings() -> AppSettings:
    return load_settings()
