"""Application settings, read from environment variables (and a .env file in development)."""

from functools import lru_cache
from pathlib import Path
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

    llm_model: str = "claude-opus-5-5"
    anthropic_api_key: SecretStr | None = Field(default=None, description="Without it, chats say no model is set up")

    knowledge_dir: Path = Path("knowledge")
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_cache_dir: str | None = Field(default=None, description="Where the embedding model is stored")
    # Calibrated with evals/rag_eval.py: lowest relevant question 0.36, highest off-topic one 0.32.
    rag_min_score: float = Field(default=0.35, description="Passages below this similarity are ignored")

    mlflow_tracking_uri: str | None = Field(default=None, description="Tracing is off when unset")
    mlflow_experiment: str = "agent-chat"

    demo_username: str = "demo"
    demo_password: SecretStr | None = Field(
        default=None, min_length=8, description="If set, a demo user with this password is created at startup"
    )

    @field_validator("demo_password", "anthropic_api_key", mode="before")
    @classmethod
    def _empty_means_none(cls, value: object) -> object:
        """An empty value (e.g. from docker compose) means: not set."""
        return None if value == "" else value

    @property
    def psycopg_url(self) -> str:
        """The database URL in the plain form psycopg (used by LangGraph) expects."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    """Load settings once per process."""
    return Settings()  # pyright: ignore[reportCallIssue] - required values come from the environment
