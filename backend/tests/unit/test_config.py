"""Settings validation: insecure configurations fail at startup."""

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings

BASE = {"database_url": "sqlite://", "jwt_secret": SecretStr("x" * 32)}


def test_empty_demo_password_means_no_demo_user() -> None:
    assert Settings(**BASE, demo_password="").demo_password is None  # type: ignore[arg-type]


def test_empty_api_key_means_not_configured() -> None:
    assert Settings(**BASE, anthropic_api_key="").anthropic_api_key is None  # type: ignore[arg-type]


def test_short_secrets_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite://", jwt_secret=SecretStr("too-short"))
    with pytest.raises(ValidationError):
        Settings(**BASE, demo_password=SecretStr("short"))  # type: ignore[arg-type]


def test_psycopg_url_drops_the_sqlalchemy_driver() -> None:
    settings = Settings(**BASE)  # type: ignore[arg-type]
    settings.database_url = "postgresql+psycopg://u:p@h:5432/d"
    assert settings.psycopg_url == "postgresql://u:p@h:5432/d"
