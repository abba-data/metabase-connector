from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    metabase_url: str = "https://analytics.atlasauthority.com"
    metabase_api_key: str = ""
    metabase_timeout_seconds: float = 30.0
    metabase_version_pin: str = ""

    connector_host: str = "0.0.0.0"
    connector_port: int = 8000
    log_level: str = "INFO"

    default_freshness_window_days: int = 60

    connector_api_keys: str = ""

    # Audit (SEC-02). audit_store: 'sqlite' (default) or 'memory'.
    audit_store: str = "sqlite"
    audit_db_path: str = "./data/audit.sqlite"
    audit_retention_days: int = 365

    # Rate limiting (SEC-04A). Format: "<n>/<period>" where period is second/minute/hour.
    # Empty string disables rate limiting entirely.
    rate_limit_default: str = "60/minute"
    rate_limit_raw_sql: str = "30/minute"
    rate_limit_operator: str = "120/minute"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
