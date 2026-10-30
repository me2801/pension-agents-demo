"""MCP server over the same services as the REST API, protected by the same bearer tokens."""

from collections.abc import Callable
from functools import partial
from uuid import UUID

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer

from app.config import Settings
from app.domain.errors import AuthenticationError
from app.domain.models import ChatAnswer, Conversation, User, WorkflowInfo
from app.services.auth_service import SCOPE, AuthService
from app.services.container import Container

INSTRUCTIONS = (
    "Chat with the organisation's AI workflows. Call list_workflows first, then send_message. "
    "Pass the returned conversation_id to continue a conversation (e.g. to approve a draft)."
)


class JwtTokenVerifier:
    """Validates MCP bearer tokens with the same AuthService the REST API uses."""

    def __init__(self, get_auth: Callable[[], AuthService]):
        self._get_auth = get_auth

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return the token's access info, or None if it is invalid."""
        try:
            user = self._get_auth().verify(token)
        except AuthenticationError:
            return None
        return AccessToken(token=token, client_id=user.username, scopes=[SCOPE], subject=str(user.id))


def current_user() -> User:
    """The user behind the bearer token of the current MCP request."""
    token = get_access_token()
    if token is None or token.subject is None:
        raise AuthenticationError("Not authenticated")
    return User(id=UUID(token.subject), username=token.client_id)


def create_mcp_server(get_container: Callable[[], Container], settings: Settings) -> MCPServer:
    """Build the MCP server; services are resolved per call, once the app has started."""
    mcp: MCPServer = MCPServer(
        name="agent-chat",
        instructions=INSTRUCTIONS,
        token_verifier=JwtTokenVerifier(lambda: get_container().auth),
        auth=AuthSettings(
            issuer_url=settings.public_url,  # pydantic coerces str to AnyHttpUrl
            resource_server_url=f"{settings.public_url}/mcp",
            required_scopes=[SCOPE],
            validate_token_resource=False,  # JwtTokenVerifier checks the audience itself
        ),
    )

    @mcp.tool()
    async def list_workflows() -> list[WorkflowInfo]:
        """List the workflows you can send messages to."""
        return get_container().chat.list_workflows()

    @mcp.tool()
    async def list_conversations(workflow_id: str | None = None) -> list[Conversation]:
        """List your conversations, most recent first, optionally for one workflow."""
        user = current_user()
        return await anyio.to_thread.run_sync(partial(get_container().chat.list_conversations, user, workflow_id))

    @mcp.tool()
    async def send_message(workflow_id: str, message: str, conversation_id: str | None = None) -> ChatAnswer:
        """Send a message to a workflow; omit conversation_id to start a new conversation."""
        user = current_user()
        existing = UUID(conversation_id) if conversation_id else None
        ask = partial(get_container().chat.ask, user, workflow_id, message, existing)
        return await anyio.to_thread.run_sync(ask)

    return mcp
