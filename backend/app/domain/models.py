"""Pydantic models: the single source of truth for REST, MCP, services and workflows.

The REST API's OpenAPI spec is generated from these models, and the frontend's TypeScript
types are generated from that spec, so all layers share one definition.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel


class DomainModel(BaseModel):
    """Base for all domain models.

    Fields with defaults are always present in responses, so the OpenAPI response schemas mark
    them required (and the generated TypeScript types are non-optional).
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class User(DomainModel):
    """An authenticated user."""

    model_config = ConfigDict(frozen=True, json_schema_serialization_defaults_required=True)

    id: UUID
    username: str


class Token(DomainModel):
    """An issued access token (OAuth2 bearer token response)."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - the OAuth2 token type, not a secret
    expires_in: int = Field(description="Lifetime in seconds")


class WorkflowInfo(DomainModel):
    """What the UI needs to know to offer a workflow."""

    id: str
    name: str
    description: str
    input_hint: str
    examples: dict[str, str] = Field(description="Button label -> message to send")


class Conversation(DomainModel):
    """A chat thread with one workflow, owned by one user."""

    id: UUID
    workflow_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class Message(DomainModel):
    """One chat message as shown in the UI."""

    id: UUID
    role: Literal["user", "assistant"]
    content: str = Field(description="Markdown")
    steps: list[str] = Field(default_factory=list, description="Progress steps behind this answer")
    choices: list[str] = Field(default_factory=list, description="Quick replies offered to the user")
    created_at: datetime


class Step(DomainModel):
    """A progress update while a workflow runs (e.g. 'calling get_forecast')."""

    type: Literal["step"] = "step"
    text: str


class Reply(DomainModel):
    """The workflow's answer that ends a turn."""

    type: Literal["reply"] = "reply"
    text: str = Field(description="Markdown")
    choices: list[str] = Field(default_factory=list, description="Quick replies the UI shows as buttons")


class NewConversation(DomainModel):
    """Request body to start a conversation."""

    workflow_id: str


class SendMessage(DomainModel):
    """Request body to send a message in a conversation."""

    content: str = Field(min_length=1, max_length=20_000)


class ChatEventStarted(DomainModel):
    """First event of a streamed turn: the stored user message."""

    type: Literal["started"] = "started"
    message: Message


class ChatEventDone(DomainModel):
    """Last event of a streamed turn: the stored assistant message."""

    type: Literal["done"] = "done"
    message: Message


class ChatEventError(DomainModel):
    """The turn failed; the error is also stored as an assistant message."""

    type: Literal["error"] = "error"
    message: Message


ChatEvent = ChatEventStarted | Step | ChatEventDone | ChatEventError


class ChatEventSchema(RootModel[Annotated[ChatEvent, Field(discriminator="type")]]):
    """One server-sent event of a chat turn (documents the stream in the OpenAPI spec)."""


class ChatAnswer(DomainModel):
    """The outcome of a non-streamed chat turn (used by MCP clients)."""

    conversation_id: UUID
    message: Message
