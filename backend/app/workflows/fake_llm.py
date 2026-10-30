"""A deterministic stand-in for Claude, for tests and end-to-end runs (LLM_PROVIDER=fake).

It is a real LangChain chat model, so workflows run unchanged; only the answers are scripted.
"""

import re
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool
from pydantic import BaseModel, PrivateAttr

from app.workflows.support import Classification, Review

KNOWN_CITIES = ("Amsterdam", "Barcelona", "Paris", "Utrecht")


def _as_text(value: LanguageModelInput) -> str:
    """Flatten a model input to plain text."""
    return value if isinstance(value, str) else str(value)


class FakeChatModel(BaseChatModel):
    """Scripted chat model: calls the weather tool once, drafts canned replies, classifies by keyword."""

    review_rejections: int = 0  # how many reviews reject a draft before approving
    tools_bound: bool = False
    _reviews: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = self._tool_turn(messages) if self.tools_bound else self._draft(messages[-1])
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        """Return a copy that answers in tool-calling mode."""
        return self.model_copy(update={"tools_bound": True})

    def with_structured_output(
        self,
        schema: dict[str, Any] | type,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, dict[str, Any] | BaseModel]:
        """Return a runnable producing a scripted Classification or Review."""
        if schema is Classification:
            return RunnableLambda(lambda value: self._classify(_as_text(value)))
        return RunnableLambda(lambda _value: self._review())

    @staticmethod
    def _tool_turn(messages: list[BaseMessage]) -> AIMessage:
        """First ask for the weather tool, then answer from its result."""
        last = messages[-1]
        if isinstance(last, ToolMessage):
            return AIMessage(f"(fake model) Based on `{last.name}`: {str(last.content)[:200]}")
        city = next((c for c in KNOWN_CITIES if c.lower() in str(last.text).lower()), "Utrecht")
        return AIMessage("", tool_calls=[{"name": "get_current_weather", "args": {"city": city}, "id": "fake-1"}])

    @staticmethod
    def _draft(prompt: BaseMessage) -> AIMessage:
        """A canned reply draft."""
        revised = " (revised)" if "FEEDBACK TO ADDRESS" in str(prompt.text) else ""
        return AIMessage(f"Dear member,\n\nThank you for your email. This is a fake draft{revised}.\n\nMember Service")

    @staticmethod
    def _classify(text: str) -> Classification:
        """Keyword-based classification."""
        member = re.search(r"\b\d{6}\b", text)
        category = "complaint" if re.search(r"klacht|complaint", text, re.IGNORECASE) else "other"
        return Classification(category=category, member_id=member.group() if member else None, query_en=text[:200])

    def _review(self) -> Review:
        """Reject the first `review_rejections` drafts, then approve."""
        self._reviews += 1
        if self._reviews <= self.review_rejections:
            return Review(approved=False, feedback="Mention the free written estimate.")
        return Review(approved=True, feedback="")
