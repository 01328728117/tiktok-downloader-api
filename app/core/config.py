"""Environment-based application configuration via Pydantic BaseSettings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "TikTok Downloader API"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", description="development|staging|production")
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # Auth — comma-separated list of allowed API keys. Empty disables auth.
    api_keys: str = ""
    api_key_header: str = "X-API-Key"

    # CORS
    cors_origins: str = "*"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"
    cors_allow_headers: str = "*"

    # Rate limiting (default: 60 req/min per IP)
    rate_limit: str = "60/minute"
    rate_limit_enabled: bool = True

    # Redis / Cache
    redis_url: str = ""
    cache_ttl_seconds: int = 3600  # 1 hour
    cache_prefix: str = "tiktok-dl:"

    # Celery
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    celery_task_always_eager: bool = False
    celery_task_time_limit: int = 120
    celery_task_soft_time_limit: int = 100

    # yt-dlp
    ytdlp_socket_timeout: int = 20
    ytdlp_retries: int = 3
    ytdlp_user_agent: str = (
        "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    )

    # Public docs
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"
    openapi_url: str = "/openapi.json"

    @field_validator("celery_broker_url", mode="before")
    @classmethod
    def _default_broker(cls, v: str | None, info) -> str:
        if v:
            return v
        return info.data.get("redis_url", "") or ""

    @field_validator("celery_result_backend", mode="before")
    @classmethod
    def _default_backend(cls, v: str | None, info) -> str:
        if v:
            return v
        return info.data.get("redis_url", "") or ""

    @property
    def allowed_api_keys(self) -> set[str]:
        """Parse comma-separated API keys into a set."""
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def use_eager_celery(self) -> bool:
        """If no broker is configured, run Celery tasks in the current process."""
        return self.celery_task_always_eager or not self.celery_broker_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the settings cache (useful for tests)."""
    get_settings.cache_clear()
