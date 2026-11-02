"""MLflow tracing: off by default; when on, a chat turn becomes one trace including the retrieval span."""

from collections.abc import Iterator
from pathlib import Path

import mlflow
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app import observability
from app.rag.memory import InMemoryKnowledgeBase
from app.workflows.policy_assistant import PolicyAssistantWorkflow
from tests.conftest import TEST_MIN_SCORE
from tests.fakes.fake_llm import FakeChatModel


@pytest.fixture
def tracing(tmp_path: Path) -> Iterator[None]:
    observability.configure_tracing(f"sqlite:///{tmp_path / 'mlflow.db'}", "test")
    yield
    mlflow.langchain.autolog(disable=True)
    observability.configure_tracing(None, "unused")
    observability._state["enabled"] = False


def test_tracing_is_off_without_a_tracking_uri(knowledge: InMemoryKnowledgeBase) -> None:
    observability.configure_tracing(None, "unused")
    assert knowledge.search("partner pension", k=1)  # still works, just untraced
    assert observability._state["enabled"] is False


@pytest.mark.usefixtures("tracing")
def test_a_turn_is_one_trace_with_retrieval_and_session(knowledge: InMemoryKnowledgeBase) -> None:
    workflow = PolicyAssistantWorkflow(FakeChatModel(), InMemorySaver(), knowledge, TEST_MIN_SCORE)
    list(workflow.stream("conversation-42", "How much partner pension does my partner receive?"))
    mlflow.flush_trace_async_logging()

    trace = mlflow.get_trace(str(mlflow.get_last_active_trace_id()))
    span_types = {span.span_type for span in trace.data.spans}
    assert {"CHAIN", "RETRIEVER", "CHAT_MODEL"} <= span_types
    assert trace.info.trace_metadata["mlflow.trace.session"] == "conversation-42"
