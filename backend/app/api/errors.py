"""Translate domain errors into HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import AuthenticationError, DomainError, NotFoundError, UnknownWorkflowError

_STATUS: dict[type[DomainError], int] = {
    AuthenticationError: 401,
    NotFoundError: 404,
    UnknownWorkflowError: 422,
}


async def _handle_domain_error(_request: Request, exc: Exception) -> JSONResponse:
    """Map a DomainError to its status code; its message is safe to show to users."""
    status = next((code for cls, code in _STATUS.items() if isinstance(exc, cls)), 400)
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse({"detail": str(exc)}, status_code=status, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    """Install the handlers on the app."""
    app.add_exception_handler(DomainError, _handle_domain_error)
