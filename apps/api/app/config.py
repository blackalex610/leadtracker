"""Infrastructure configuration loaded from environment variables.

Runtime-editable preferences (scoring weights, calling hours, audit limits, ...)
live in the database and are managed by ``app.services.settings``. Values here
act as their initial defaults where relevant. Secrets (provider API keys, the
session secret) are only ever read from the environment.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _API_DIR.parent.parent

INSECURE_DEFAULT_SECRET = "dev-insecure-secret-change-me"  # noqa: S105 - sentinel, rejected in token mode
DEFAULT_DATABASE_URL = "postgresql+asyncpg://leadtracker:leadtracker@localhost:5432/leadtracker"

# libpq/Prisma-only URL parameters that asyncpg does not understand.
_DROPPED_URL_PARAMS = {"channel_binding", "pgbouncer", "connection_limit", "pool_timeout", "gssencmode"}


def _on_public_vercel() -> bool:
    return os.environ.get("VERCEL_ENV") in ("production", "preview")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), str(_API_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Deployed Vercel environments default to production (JSON logs, HSTS, secure cookies).
    environment: Literal["development", "test", "production"] = Field(
        default_factory=lambda: "production" if _on_public_vercel() else "development"
    )
    app_version: str = "1.0.0"

    # The direct (non-pooled) URL is preferred when a platform integration provides both,
    # e.g. Neon on Vercel sets DATABASE_URL (pooled) and DATABASE_URL_UNPOOLED.
    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        validation_alias=AliasChoices(
            "DATABASE_URL_UNPOOLED", "POSTGRES_URL_NON_POOLING", "DATABASE_URL", "POSTGRES_URL"
        ),
    )
    database_pool_size: int = 10

    # --- Business data provider -------------------------------------------------
    provider: Literal["google_places"] = "google_places"
    provider_api_key: SecretStr | None = Field(default=None)
    provider_base_url: str = "https://places.googleapis.com/v1"
    provider_timeout_seconds: float = 20.0
    # "enterprise" returns phone/website/rating/hours in the Text Search call itself.
    # "enterprise_atmosphere" additionally requests the editorial description (more expensive).
    places_field_tier: Literal["enterprise", "enterprise_atmosphere"] = "enterprise"
    demo_mode: bool = False

    default_country: str = "BG"
    default_city: str = "Sofia"
    default_language: str = "bg"
    timezone: str = "Europe/Sofia"

    # --- Website auditing -------------------------------------------------------
    website_audit_timeout: int = 10000  # milliseconds, per request
    max_concurrent_audits: int = 5
    audit_user_agent: str = "LeadTrackerAudit/1.0 (+website-audit; respects robots.txt)"
    pagespeed_api_key: SecretStr | None = None

    # --- Server -----------------------------------------------------------------
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Serverless platforms (Vercel) have no long-running process: background jobs then run in
    # time-boxed slices triggered by the app (POST /api/worker/run) and a daily cron.
    # Detected automatically on Vercel; SERVERLESS=true forces it elsewhere.
    serverless: bool = Field(default_factory=lambda: bool(os.environ.get("VERCEL")))
    run_worker: bool | None = None  # default: true, false when serverless
    run_migrations: bool | None = None  # apply migrations on startup; default: true when serverless
    worker_concurrency: int = 2
    worker_poll_interval_seconds: float = 1.0
    worker_run_budget_seconds: int = 40
    cron_secret: SecretStr | None = None

    auth_mode: Literal["none", "token"] = "none"
    secret_key: SecretStr = SecretStr(INSECURE_DEFAULT_SECRET)
    session_cookie_name: str = "lt_session"
    session_cookie_secure: bool = Field(default_factory=lambda: _on_public_vercel())
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_max_age_hours: int = 24 * 14
    # Creates/updates an admin user with this token on startup (for platforms without a shell).
    admin_email: str = "admin@leadtracker.local"
    admin_token: SecretStr | None = None
    # Public hosting with AUTH_MODE=none is refused unless this is set explicitly.
    allow_open_access: bool = False

    log_level: str = "INFO"
    log_json: bool | None = None

    # Google Maps Platform terms allow caching lat/lng for at most 30 days.
    google_latlng_retention_days: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("provider_api_key", "pagespeed_api_key", "admin_token", "cron_secret", mode="before")
    @classmethod
    def _empty_secret_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, value: str) -> str:
        """Accept the plain URLs managed providers hand out (postgres://, ?sslmode=...)."""
        return normalize_database_url(value)

    @field_validator("secret_key", mode="before")
    @classmethod
    def _empty_secret_key(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return INSECURE_DEFAULT_SECRET
        return value

    @field_validator("default_country")
    @classmethod
    def _upper_country(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def _check_security(self) -> Settings:
        secret = self.secret_key.get_secret_value()
        if self.auth_mode == "token" and (secret == INSECURE_DEFAULT_SECRET or len(secret) < 32):
            raise ValueError(
                "SECRET_KEY must be a random value of at least 32 characters when AUTH_MODE=token"
            )
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true when SESSION_COOKIE_SAMESITE=none")
        if self.admin_token is not None and len(self.admin_token.get_secret_value()) < 24:
            raise ValueError("ADMIN_TOKEN must be at least 24 characters")
        return self

    @property
    def embedded_worker(self) -> bool:
        return self.run_worker if self.run_worker is not None else not self.serverless

    @property
    def on_demand_worker(self) -> bool:
        """Jobs are processed by POST /api/worker/run instead of a resident worker."""
        return self.serverless and not self.embedded_worker

    @property
    def migrate_on_startup(self) -> bool:
        return self.run_migrations if self.run_migrations is not None else self.serverless

    @property
    def publicly_hosted(self) -> bool:
        return _on_public_vercel()

    def setup_problems(self) -> list[str]:
        """Configuration mistakes that make a public deployment unsafe or unusable."""
        problems: list[str] = []
        if self.publicly_hosted and self.auth_mode == "none" and not self.allow_open_access:
            problems.append(
                "AUTH_MODE=none on a public deployment: set AUTH_MODE=token, SECRET_KEY and ADMIN_TOKEN "
                "(or ALLOW_OPEN_ACCESS=true if the site is protected another way)."
            )
        if self.publicly_hosted and self.database_url == DEFAULT_DATABASE_URL:
            problems.append(
                "DATABASE_URL is not set: connect a Postgres database (e.g. Neon) to the project."
            )
        return problems

    @property
    def provider_configured(self) -> bool:
        return self.provider_api_key is not None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def use_json_logs(self) -> bool:
        return self.log_json if self.log_json is not None else self.is_production


def normalize_database_url(value: str) -> str:
    """postgres:// → postgresql+asyncpg://, sslmode → ssl, and drop parameters asyncpg rejects."""
    value = value.strip()
    for prefix in ("postgres://", "postgresql://"):
        if value.startswith(prefix):
            value = "postgresql+asyncpg://" + value[len(prefix) :]
    parts = urlsplit(value)
    if not parts.query:
        return value
    params = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        if key in _DROPPED_URL_PARAMS:
            continue
        params.append(("ssl" if key == "sslmode" else key, val))
    return urlunsplit(parts._replace(query=urlencode(params)))


@lru_cache
def get_settings() -> Settings:
    return Settings()
