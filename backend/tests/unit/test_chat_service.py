"""Chat use cases, including authorization and swapping in another ChatWorkflow implementation."""

import uuid
from collections.abc import Iterator

import pytest

from app.domain.errors import NotFoundError, UnknownWorkflowError
from app.domain.models import ChatEventDone, ChatEventError, ChatEventStarted, Reply, Step, User
from app.services.chat_service import ChatService
from app.services.container import Container
from app.workflows.base import ChatWorkflow

STRANGER = User(id=uuid.uuid4(), username="stranger")


class EchoWorkflow(ChatWorkflow):
    """A non-LangGraph implementation of the interface: proves workflows are swappable."""

    id = "echo"
    name = "Echo"
    description = "Repeats the message."

    def stream(self, thread_id: str, message: str) -> Iterator[Step | Reply]:
        yield Step(text="echoing")
        yield Reply(text=message.upper(), choices=["again"])


class BrokenWorkflow(EchoWorkflow):
    """Fails halfway through a turn."""

    id = "broken"

    def stream(self, thread_id: str, message: str) -> Iterator[Step | Reply]:
        yield Step(text="about to fail")
        raise RuntimeError("secret internal details")


class SilentWorkflow(EchoWorkflow):
    """Violates the contract by never replying."""

    id = "silent"

    def stream(self, thread_id: str, message: str) -> Iterator[Step | Reply]:
        yield Step(text="nothing to say")


@pytest.fixture
def demo_user(container: Container) -> User:
    return container.auth.verify(container.auth.login("demo", "correct horse battery staple").access_token)


@pytest.fixture
def chat(container: Container) -> ChatService:
    workflows: dict[str, ChatWorkflow] = {w.id: w for w in (EchoWorkflow(), BrokenWorkflow(), SilentWorkflow())}
    return ChatService(container.chat._conversations, workflows)


def test_a_turn_streams_started_steps_done_and_stores_the_transcript(chat: ChatService, demo_user: User) -> None:
    conversation = chat.start_conversation(demo_user, "echo")
    events = list(chat.send_message(demo_user, conversation.id, "hello"))
    assert [type(e) for e in events] == [ChatEventStarted, Step, ChatEventDone]
    done = events[-1]
    assert isinstance(done, ChatEventDone)
    assert (done.message.content, done.message.steps, done.message.choices) == ("HELLO", ["echoing"], ["again"])
    assert [m.role for m in chat.get_messages(demo_user, conversation.id)] == ["user", "assistant"]
    assert chat.list_conversations(demo_user)[0].title == "hello"


def test_workflow_failure_becomes_a_safe_error_message(chat: ChatService, demo_user: User) -> None:
    conversation = chat.start_conversation(demo_user, "broken")
    error = list(chat.send_message(demo_user, conversation.id, "hi"))[-1]
    assert isinstance(error, ChatEventError)
    assert "Something went wrong" in error.message.content
    assert "secret internal details" not in error.message.content
    assert error.message.steps == ["about to fail"]


def test_workflow_without_reply_is_an_error(chat: ChatService, demo_user: User) -> None:
    conversation = chat.start_conversation(demo_user, "silent")
    assert isinstance(list(chat.send_message(demo_user, conversation.id, "hi"))[-1], ChatEventError)


def test_users_cannot_see_each_others_conversations(chat: ChatService, demo_user: User) -> None:
    conversation = chat.start_conversation(demo_user, "echo")
    with pytest.raises(NotFoundError):
        chat.get_messages(STRANGER, conversation.id)
    with pytest.raises(NotFoundError):
        list(chat.send_message(STRANGER, conversation.id, "hi"))
    assert chat.list_conversations(STRANGER) == []


def test_unknown_workflow_is_rejected(chat: ChatService, demo_user: User) -> None:
    with pytest.raises(UnknownWorkflowError):
        chat.start_conversation(demo_user, "nope")


def test_ask_creates_a_conversation_and_returns_the_answer(chat: ChatService, demo_user: User) -> None:
    answer = chat.ask(demo_user, "echo", "hi")
    assert answer.message.content == "HI"
    follow_up = chat.ask(demo_user, "echo", "again", answer.conversation_id)
    assert follow_up.conversation_id == answer.conversation_id
    assert len(chat.list_conversations(demo_user, "echo")) == 1
