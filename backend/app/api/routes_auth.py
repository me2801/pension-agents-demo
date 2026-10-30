"""Authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import AuthServiceDep, CurrentUser
from app.domain.models import Token, User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token", summary="Log in and get an access token")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], auth: AuthServiceDep) -> Token:
    """OAuth2 password flow: exchange username and password for a bearer token."""
    return auth.login(form.username, form.password)


@router.get("/me", summary="The current user")
def me(user: CurrentUser) -> User:
    """Who the bearer token belongs to."""
    return user
