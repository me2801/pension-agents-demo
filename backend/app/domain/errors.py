"""Domain errors. Transport layers translate them to HTTP / MCP errors."""


class DomainError(Exception):
    """Base class for expected, user-facing errors."""


class NotFoundError(DomainError):
    """The resource does not exist, or the user may not see it (we don't reveal which)."""


class AuthenticationError(DomainError):
    """Missing, invalid or expired credentials."""


class UnknownWorkflowError(DomainError):
    """The requested workflow id is not registered."""
