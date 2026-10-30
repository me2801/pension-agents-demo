"""Authentication: password login and JWT access tokens, used by both REST and MCP.

Isolated behind this service so an external identity provider (Entra ID, Cognito, Keycloak)
can replace local login without touching the transport layers.
"""

import logging
import time
from uuid import UUID

import bcrypt
import jwt

from app.config import Settings
from app.db.repositories import UserRepository
from app.domain.errors import AuthenticationError
from app.domain.models import Token, User

logger = logging.getLogger(__name__)

AUDIENCE = "mnai"
SCOPE = "chat"
_ALGORITHM = "HS256"
# Compared against when the username is unknown, so login takes equally long either way.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


class AuthService:
    """Issues and verifies access tokens."""

    def __init__(self, users: UserRepository, settings: Settings):
        self._users = users
        self._settings = settings

    def login(self, username: str, password: str) -> Token:
        """Check credentials and issue an access token."""
        found = self._users.get_with_hash(username)
        password_hash = found[1] if found else _DUMMY_HASH
        if not bcrypt.checkpw(password.encode(), password_hash.encode()) or found is None:
            logger.warning("Failed login for username=%r", username)
            raise AuthenticationError("Invalid username or password")
        return self._issue(found[0])

    def _issue(self, user: User) -> Token:
        """Create a signed JWT for a user."""
        now = int(time.time())
        ttl = self._settings.jwt_ttl_minutes * 60
        claims = {
            "sub": str(user.id),
            "name": user.username,
            "aud": AUDIENCE,
            "iss": self._settings.public_url,
            "scope": SCOPE,
            "iat": now,
            "exp": now + ttl,
        }
        token = jwt.encode(claims, self._settings.jwt_secret.get_secret_value(), algorithm=_ALGORITHM)
        return Token(access_token=token, expires_in=ttl)

    def verify(self, token: str) -> User:
        """Validate signature, expiry, audience, issuer and scope; return the user."""
        try:
            claims = jwt.decode(
                token,
                self._settings.jwt_secret.get_secret_value(),
                algorithms=[_ALGORITHM],
                audience=AUDIENCE,
                issuer=self._settings.public_url,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid or expired token") from exc
        if SCOPE not in str(claims.get("scope", "")).split():
            raise AuthenticationError("Token lacks the required scope")
        return User(id=UUID(claims["sub"]), username=claims["name"])

    def ensure_user(self, username: str, password: str) -> None:
        """Create a user if it doesn't exist yet (used to seed the demo user)."""
        if self._users.get_with_hash(username) is None:
            self._users.create(username, hash_password(password))
            logger.info("Created user %r", username)
