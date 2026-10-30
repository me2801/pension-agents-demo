"""Chat use cases: conversations, messages and running workflows.

Authorization lives here, not in the transport layers: every method takes the acting user and
only touches that user's conversations, so REST and MCP can't diverge.
"""

import logging
import uuid
from collections.abc import Generator, Iterator
from uuid import UUID

from app.db.repositories import ConversationRepository
from app.domain.errors import NotFoundError, UnknownWorkflowError
from app.domain.models import (
    ChatAnswer,
    ChatEvent,
    ChatEventDone,
    ChatEventError,
    ChatEventStarted,
    Conversation,
    Message,
    Reply,
    Step,
    User,
    WorkflowInfo,
)
from app.workflows.base import ChatWorkflow

logger = logging.getLogger(__name__)

NEW_TITLE = "New conversation"
TITLE_LENGTH = 60


class ChatService:
    """Runs chat turns against the registered workflows and stores the transcript."""

    def __init__(self, conversations: ConversationRepository, workflows: dict[str, ChatWorkflow]):
        self._conversations = conversations
        self._workflows = workflows

    def list_workflows(self) -> list[WorkflowInfo]:
        """All available workflows."""
        return [workflow.info() for workflow in self._workflows.values()]

    def start_conversation(self, user: User, workflow_id: str) -> Conversation:
        """Create an empty conversation with a workflow."""
        if workflow_id not in self._workflows:
            raise UnknownWorkflowError(f"Unknown workflow '{workflow_id}'")
        return self._conversations.create(user.id, workflow_id, NEW_TITLE)

    def list_conversations(self, user: User, workflow_id: str | None = None) -> list[Conversation]:
        """The user's conversations, most recent first."""
        return self._conversations.list_owned(user.id, workflow_id)

    def get_conversation(self, user: User, conversation_id: UUID) -> Conversation:
        """One of the user's conversations."""
        conversation = self._conversations.get_owned(conversation_id, user.id)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        return conversation

    def get_messages(self, user: User, conversation_id: UUID) -> list[Message]:
        """The transcript of one of the user's conversations."""
        self.get_conversation(user, conversation_id)
        return self._conversations.list_messages(conversation_id)

    def send_message(self, user: User, conversation_id: UUID, content: str) -> Iterator[ChatEvent]:
        """Store the message, run the workflow and stream its events; the answer is stored too."""
        conversation = self.get_conversation(user, conversation_id)
        if conversation.title == NEW_TITLE:
            self._conversations.rename(conversation_id, content[:TITLE_LENGTH])
        yield ChatEventStarted(message=self._conversations.add_message(conversation_id, "user", content))
        steps: list[str] = []
        try:
            reply = yield from self._run(conversation, content, steps)
        except Exception:  # any workflow failure becomes a chat message, never a broken stream
            reference = uuid.uuid4().hex[:8]
            logger.exception("Workflow failed (reference %s)", reference)
            text = f"⚠️ Something went wrong. Please try again (reference `{reference}`)."
            yield ChatEventError(message=self._conversations.add_message(conversation_id, "assistant", text, steps))
            return
        message = self._conversations.add_message(conversation_id, "assistant", reply.text, steps, reply.choices)
        yield ChatEventDone(message=message)

    def _run(self, conversation: Conversation, content: str, steps: list[str]) -> Generator[Step, None, Reply]:
        """Stream the workflow's steps (also collected in `steps`) and return its reply."""
        workflow = self._workflows[conversation.workflow_id]
        for event in workflow.stream(str(conversation.id), content):
            if isinstance(event, Reply):
                return event
            steps.append(event.text)
            yield event
        raise RuntimeError(f"Workflow {workflow.id} ended without a reply")

    def ask(self, user: User, workflow_id: str, content: str, conversation_id: UUID | None = None) -> ChatAnswer:
        """Non-streaming convenience: send a message (in a new conversation if none given), return the answer."""
        if conversation_id is None:
            conversation_id = self.start_conversation(user, workflow_id).id
        final: Message | None = None
        for event in self.send_message(user, conversation_id, content):
            if isinstance(event, ChatEventDone | ChatEventError):
                final = event.message
        if final is None:  # pragma: no cover - send_message always ends with done or error
            raise RuntimeError("No answer produced")
        return ChatAnswer(conversation_id=conversation_id, message=final)
