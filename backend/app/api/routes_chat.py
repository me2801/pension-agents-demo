"""Chat endpoints: workflows, conversations and streamed messages."""

from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import ChatServiceDep, CurrentUser
from app.domain.models import (
    ChatEvent,
    ChatEventSchema,
    Conversation,
    Message,
    NewConversation,
    SendMessage,
    WorkflowInfo,
)

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.get("/workflows", summary="List available workflows")
def list_workflows(_user: CurrentUser, chat: ChatServiceDep) -> list[WorkflowInfo]:
    """Workflows the user can chat with."""
    return chat.list_workflows()


@router.get("/conversations", summary="List my conversations")
def list_conversations(user: CurrentUser, chat: ChatServiceDep, workflow_id: str | None = None) -> list[Conversation]:
    """The user's conversations, most recently active first, optionally for one workflow."""
    return chat.list_conversations(user, workflow_id)


@router.post("/conversations", status_code=201, summary="Start a conversation")
def start_conversation(body: NewConversation, user: CurrentUser, chat: ChatServiceDep) -> Conversation:
    """Create an empty conversation with a workflow."""
    return chat.start_conversation(user, body.workflow_id)


@router.get("/conversations/{conversation_id}/messages", summary="Get a conversation's messages")
def get_messages(conversation_id: UUID, user: CurrentUser, chat: ChatServiceDep) -> list[Message]:
    """The transcript, oldest first."""
    return chat.get_messages(user, conversation_id)


def _sse(events: Iterator[ChatEvent]) -> Iterator[str]:
    """Encode events in the server-sent events wire format."""
    for event in events:
        yield f"data: {event.model_dump_json()}\n\n"


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Send a message (streamed)",
    response_class=StreamingResponse,
    responses={
        200: {
            "model": ChatEventSchema,
            "description": "A text/event-stream; every `data:` line is one ChatEvent: "
            "`started`, any number of `step`, then `done` or `error`.",
        }
    },
)
def send_message(
    conversation_id: UUID, body: SendMessage, user: CurrentUser, chat: ChatServiceDep
) -> StreamingResponse:
    """Run the workflow on a message and stream its progress as server-sent events."""
    chat.get_conversation(user, conversation_id)  # fail with 404 before the stream starts
    return StreamingResponse(
        _sse(chat.send_message(user, conversation_id, body.content)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
