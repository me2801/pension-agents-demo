"""A deterministic stand-in for Claude, for tests and end-to-end runs (injected, never part of the app).

It is a real LangChain chat model, so workflows run unchanged; only the answers are scripted.
"""

import json
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
WET_CONDITIONS = ("rain", "drizzle", "shower", "thunder", "snow")
DEMO_NOTE = "\n\n_Demo mode: scripted answer. Configure an Anthropic API key for answers from Claude._"


def _as_text(value: LanguageModelInput) -> str:
    """Flatten a model input to plain text."""
    return value if isinstance(value, str) else str(value)


def _weather_answer(tool: ToolMessage) -> str:
    """Turn the weather tool's result into a short, practical answer."""
    if tool.status == "error":
        return "Sorry, I couldn't find that location. Could you check the spelling?" + DEMO_NOTE
    data = json.loads(str(tool.content))
    wet = any(word in data["conditions"] for word in WET_CONDITIONS)
    advice = "Take an umbrella." if wet else "No umbrella needed."
    return (
        f"In {data['location']} it's {data['temperature_c']:.0f}°C right now "
        f"(feels like {data['feels_like_c']:.0f}°C) with {data['conditions']} "
        f"and a wind of {data['wind_kmh']:.0f} km/h. {advice}" + DEMO_NOTE
    )


def _rag_answer(system_prompt: str) -> str:
    """Answer by quoting the first sentence of the best source, with a citation."""
    source = re.search(r"SOURCES:\n\[1\] [^\n]+\n(.+?\.)(?:\s|$)", system_prompt, re.DOTALL)
    if not source:
        return "The sources don't answer this question." + DEMO_NOTE
    return f"According to the policy documents: {' '.join(source.group(1).split())} [1]" + DEMO_NOTE


def _draft_text(prompt: str) -> str:
    """A reply letter built from the member data and the most relevant policy in the prompt."""
    name = re.search(r"'name': '([^']+)'", prompt)
    policy = re.search(r"POLICIES:\n- [^:\n]+: ([^\n]+)", prompt)
    greeting = f"Dear {name.group(1)}," if name else "Dear member,"
    answer = policy.group(1) if policy else "We have received your question and will get back to you shortly."
    answer = answer[:1].upper() + answer[1:]
    follow_up = "\n\nWe have also taken your feedback into account." if "FEEDBACK TO ADDRESS" in prompt else ""
    return f"{greeting}\n\nThank you for your email. {answer}{follow_up}\n\nKind regards,\nMember Service"


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
        if self.tools_bound:
            message = self._tool_turn(messages)
        elif "SOURCES:" in str(messages[0].text):  # the policy assistant's RAG prompt
            message = AIMessage(_rag_answer(str(messages[0].text)))
        else:
            message = self._draft(messages[-1])
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
            return AIMessage(_weather_answer(last))
        city = next((c for c in KNOWN_CITIES if c.lower() in str(last.text).lower()), "Utrecht")
        return AIMessage("", tool_calls=[{"name": "get_current_weather", "args": {"city": city}, "id": "fake-1"}])

    @staticmethod
    def _draft(prompt: BaseMessage) -> AIMessage:
        """A reply draft (rewrites acknowledge the feedback)."""
        return AIMessage(_draft_text(str(prompt.text)))

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
