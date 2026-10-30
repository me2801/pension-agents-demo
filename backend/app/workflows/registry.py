"""Build the chat model and the registered workflows. To add a workflow: implement ChatWorkflow, list it here."""

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.config import Settings
from app.workflows.base import ChatWorkflow
from app.workflows.fake_llm import FakeChatModel
from app.workflows.support import SupportWorkflow
from app.workflows.weather import WeatherWorkflow

WORKFLOW_CLASSES: tuple[type[WeatherWorkflow | SupportWorkflow], ...] = (WeatherWorkflow, SupportWorkflow)


def create_chat_model(settings: Settings) -> BaseChatModel:
    """The chat model all workflows use. The fake provider is refused in production."""
    if settings.llm_provider == "fake":
        if settings.environment == "production":
            raise ValueError("LLM_PROVIDER=fake is not allowed in production")
        return FakeChatModel()
    return ChatAnthropic(model=settings.llm_model, max_tokens=16000)


def build_workflows(llm: BaseChatModel, checkpointer: BaseCheckpointSaver[Any]) -> dict[str, ChatWorkflow]:
    """Instantiate every registered workflow, keyed by id."""
    return {cls.id: cls(llm, checkpointer) for cls in WORKFLOW_CLASSES}
