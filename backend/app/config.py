"""Application settings, read from environment variables (and a .env file in development)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Secrets have no defaults, so a missing one fails at startup."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(
        description="SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:5432/db",
    )
    jwt_secret: SecretStr = Field(min_length=32, description="HMAC key for signing access tokens")
    jwt_ttl_minutes: int = 60
    public_url: str = "http://localhost:8000"
    cors_origins: list[str] = ["http://localhost:5173"]
    mcp_allowed_hosts: list[str] = ["localhost:*", "127.0.0.1:*"]

    llm_provider: Literal["anthropic", "fake"] = "anthropic"
    llm_model: str = "claude-opus-5-5"

    demo_username: str = "demo"
    demo_password: SecretStr | None = Field(
        default=None, min_length=8, description="If set, a demo user with this password is created at startup"
    )

    @field_validator("demo_password", mode="before")
    @classmethod
    def _empty_means_none(cls, value: object) -> object:
        """An empty DEMO_PASSWORD (e.g. from docker compose) means: no demo user."""
        return None if value == "" else value

    @property
    def psycopg_url(self) -> str:
        """The database URL in the plain form psycopg (used by LangGraph) expects."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    """Load settings once per process."""
    return Settings()  # pyright: ignore[reportCallIssue] - required values come from the environment
