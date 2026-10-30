"""The contract every chat workflow implements, so services and UIs can swap them freely.

Callers only know this interface: they send a user message and get progress steps and a reply.
How a workflow works inside (LangGraph, a plain SDK loop, a rules engine, ...) is its own business.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import ClassVar

from app.domain.models import Reply, Step, WorkflowInfo


class ChatWorkflow(ABC):
    """A conversational workflow that keeps its own state per thread."""

    id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    input_hint: ClassVar[str] = "Type a message"
    examples: ClassVar[dict[str, str]] = {}

    def info(self) -> WorkflowInfo:
        """Describe this workflow for clients."""
        return WorkflowInfo(
            id=self.id,
            name=self.name,
            description=self.description,
            input_hint=self.input_hint,
            examples=self.examples,
        )

    @abstractmethod
    def stream(self, thread_id: str, message: str) -> Iterator[Step | Reply]:
        """Handle one user message in a conversation.

        Yields any number of Steps, then exactly one Reply. Implementations keep their own
        state per thread_id, so a conversation can continue later (even after a restart).
        """
