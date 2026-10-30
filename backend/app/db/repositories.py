"""Repositories: the only code that talks SQL. They take and return domain models, never ORM rows.

Each method runs in its own short transaction, so callers (including long-running streamed
responses) never hold a database session open.
"""

from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.tables import ConversationRow, MessageRow, UserRow, utcnow
from app.domain.models import Conversation, Message, User


def _conversation(row: ConversationRow) -> Conversation:
    """Map a row to the domain model."""
    return Conversation(
        id=row.id,
        workflow_id=row.workflow_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message(row: MessageRow) -> Message:
    """Map a row to the domain model."""
    return Message(
        id=row.id,
        role="user" if row.role == "user" else "assistant",
        content=row.content,
        steps=list(row.steps),
        choices=list(row.choices),
        created_at=row.created_at,
    )


class UserRepository:
    """Users and their password hashes."""

    def __init__(self, sessions: sessionmaker[Session]):
        self._sessions = sessions

    def get_with_hash(self, username: str) -> tuple[User, str] | None:
        """A user plus password hash, for login."""
        with self._sessions() as session:
            row = session.scalar(select(UserRow).where(UserRow.username == username))
            return (User(id=row.id, username=row.username), row.password_hash) if row else None

    def create(self, username: str, password_hash: str) -> User:
        """Create a user."""
        with self._sessions.begin() as session:
            row = UserRow(username=username, password_hash=password_hash)
            session.add(row)
            session.flush()
            return User(id=row.id, username=row.username)


class ConversationRepository:
    """Conversations and their displayed messages."""

    def __init__(self, sessions: sessionmaker[Session]):
        self._sessions = sessions

    def create(self, user_id: UUID, workflow_id: str, title: str) -> Conversation:
        """Start a conversation."""
        with self._sessions.begin() as session:
            row = ConversationRow(user_id=user_id, workflow_id=workflow_id, title=title)
            session.add(row)
            session.flush()
            return _conversation(row)

    def get_owned(self, conversation_id: UUID, user_id: UUID) -> Conversation | None:
        """A conversation, only if it belongs to the user."""
        with self._sessions() as session:
            row = session.get(ConversationRow, conversation_id)
            return _conversation(row) if row and row.user_id == user_id else None

    def list_owned(self, user_id: UUID, workflow_id: str | None = None, limit: int = 50) -> list[Conversation]:
        """The user's conversations, most recently active first."""
        query = select(ConversationRow).where(ConversationRow.user_id == user_id)
        if workflow_id:
            query = query.where(ConversationRow.workflow_id == workflow_id)
        with self._sessions() as session:
            rows = session.scalars(query.order_by(ConversationRow.updated_at.desc()).limit(limit))
            return [_conversation(row) for row in rows]

    def rename(self, conversation_id: UUID, title: str) -> None:
        """Change a conversation's title."""
        with self._sessions.begin() as session:
            row = session.get_one(ConversationRow, conversation_id)
            row.title = title

    def add_message(
        self,
        conversation_id: UUID,
        role: Literal["user", "assistant"],
        content: str,
        steps: list[str] | None = None,
        choices: list[str] | None = None,
    ) -> Message:
        """Append a message and mark the conversation as recently active."""
        with self._sessions.begin() as session:
            row = MessageRow(
                conversation_id=conversation_id,
                role=role,
                content=content,
                steps=steps or [],
                choices=choices or [],
            )
            session.add(row)
            session.get_one(ConversationRow, conversation_id).updated_at = utcnow()
            session.flush()
            return _message(row)

    def list_messages(self, conversation_id: UUID) -> list[Message]:
        """All messages of a conversation, oldest first."""
        query = select(MessageRow).where(MessageRow.conversation_id == conversation_id)
        with self._sessions() as session:
            return [_message(row) for row in session.scalars(query.order_by(MessageRow.created_at))]
