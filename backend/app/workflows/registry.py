"""Build the chat model and the registered workflows. To add a workflow: implement ChatWorkflow, list it here."""

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.config import Settings
from app.rag.base import KnowledgeBase
from app.workflows.base import ChatWorkflow
from app.workflows.policy_assistant import PolicyAssistantWorkflow
from app.workflows.support import SupportWorkflow
from app.workflows.weather import WeatherWorkflow


def create_chat_model(settings: Settings) -> BaseChatModel:
    """The chat model all workflows use. Without an API key it is never invoked (ChatService says so)."""
    return ChatAnthropic(model=settings.llm_model, max_tokens=16000, api_key=settings.anthropic_api_key)


def build_workflows(
    llm: BaseChatModel,
    checkpointer: BaseCheckpointSaver[Any],
    knowledge: KnowledgeBase,
    rag_min_score: float,
) -> dict[str, ChatWorkflow]:
    """Instantiate every registered workflow, keyed by id."""
    workflows: list[ChatWorkflow] = [
        WeatherWorkflow(llm, checkpointer),
        SupportWorkflow(llm, checkpointer, knowledge),
        PolicyAssistantWorkflow(llm, checkpointer, knowledge, rag_min_score),
    ]
    return {workflow.id: workflow for workflow in workflows}
