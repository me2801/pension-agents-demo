"""The service container that transport layers receive via dependency injection."""

from collections.abc import Callable
from dataclasses import dataclass, field

from app.config import Settings
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService


@dataclass
class Container:
    """Everything the REST API and MCP server need, wired once at startup."""

    settings: Settings
    auth: AuthService
    chat: ChatService
    closers: list[Callable[[], None]] = field(default_factory=list)

    def close(self) -> None:
        """Release resources (connection pools) in reverse order of creation."""
        for close in reversed(self.closers):
            close()
