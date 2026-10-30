"""Login and token verification."""

import time

import jwt
import pytest

from app.domain.errors import AuthenticationError
from app.services.auth_service import AUDIENCE
from app.services.container import Container
from tests.conftest import PASSWORD


def test_login_issues_a_token_that_verifies(container: Container) -> None:
    token = container.auth.login("demo", PASSWORD)
    assert token.token_type == "bearer"
    assert container.auth.verify(token.access_token).username == "demo"


@pytest.mark.parametrize(("username", "password"), [("demo", "wrong"), ("nobody", PASSWORD)])
def test_bad_credentials_are_rejected(container: Container, username: str, password: str) -> None:
    with pytest.raises(AuthenticationError, match="Invalid username or password"):
        container.auth.login(username, password)


def _forge(container: Container, secret: str | None = None, **overrides: object) -> str:
    claims = {
        "sub": "6d0f0c2e-0000-4000-8000-000000000000",
        "name": "demo",
        "aud": AUDIENCE,
        "iss": container.settings.public_url,
        "scope": "chat",
        "exp": int(time.time()) + 60,
    } | overrides
    key = secret or container.settings.jwt_secret.get_secret_value()
    return jwt.encode(claims, key, algorithm="HS256")


@pytest.mark.parametrize(
    "token_kwargs",
    [
        {"secret": "another-secret-that-is-at-least-32-characters"},
        {"exp": int(time.time()) - 10},
        {"aud": "someone-else"},
        {"iss": "https://evil.example"},
    ],
    ids=["wrong-signature", "expired", "wrong-audience", "wrong-issuer"],
)
def test_invalid_tokens_are_rejected(container: Container, token_kwargs: dict[str, object]) -> None:
    secret = token_kwargs.pop("secret", None)
    with pytest.raises(AuthenticationError, match="Invalid or expired token"):
        container.auth.verify(_forge(container, secret=str(secret) if secret else None, **token_kwargs))


def test_token_without_scope_is_rejected(container: Container) -> None:
    with pytest.raises(AuthenticationError, match="scope"):
        container.auth.verify(_forge(container, scope="other"))
