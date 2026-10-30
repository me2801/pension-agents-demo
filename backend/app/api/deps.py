"""FastAPI dependency providers: how routes receive services and the current user."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from app.domain.models import User
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.container import Container

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_container(request: Request) -> Container:
    """The service container created at startup."""
    container: Container = request.app.state.container
    return container


def get_auth_service(container: Annotated[Container, Depends(get_container)]) -> AuthService:
    """The authentication service."""
    return container.auth


def get_chat_service(container: Annotated[Container, Depends(get_container)]) -> ChatService:
    """The chat service."""
    return container.chat


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], auth: AuthServiceDep) -> User:
    """The user behind the bearer token (401 if invalid, via the error handlers)."""
    return auth.verify(token)


CurrentUser = Annotated[User, Depends(get_current_user)]
