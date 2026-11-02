"""The RAG workflow: grounded answers with sources, and no answer when nothing relevant is found."""

from langgraph.checkpoint.memory import InMemorySaver

from app.domain.models import Reply, Step
from app.rag.memory import InMemoryKnowledgeBase
from app.workflows.policy_assistant import NO_ANSWER, PolicyAssistantWorkflow
from tests.conftest import TEST_MIN_SCORE
from tests.fakes.fake_llm import FakeChatModel


def ask(workflow: PolicyAssistantWorkflow, thread: str, question: str) -> tuple[list[str], Reply]:
    *steps, reply = workflow.stream(thread, question)
    assert isinstance(reply, Reply)
    return [s.text for s in steps if isinstance(s, Step)], reply


def test_answers_from_the_documents_with_sources(knowledge: InMemoryKnowledgeBase) -> None:
    workflow = PolicyAssistantWorkflow(FakeChatModel(), InMemorySaver(), knowledge, TEST_MIN_SCORE)
    steps, reply = ask(workflow, "p1", "What percentage partner pension does the registered partner receive?")
    assert steps[0].startswith("retrieve: 4 relevant passages, best match")
    assert steps[1] == "generate: answer from 4 sources"
    assert "[1]" in reply.text
    assert "**Sources**" in reply.text
    assert "(`partner-pension.md`)" in reply.text


def test_says_so_when_nothing_relevant_is_found(knowledge: InMemoryKnowledgeBase) -> None:
    workflow = PolicyAssistantWorkflow(FakeChatModel(), InMemorySaver(), knowledge, TEST_MIN_SCORE)
    # No word the documents share: the test embeddings ignore words shorter than 3 letters.
    steps, reply = ask(workflow, "p2", "Hm, ok?")
    assert steps == ["retrieve: 0 relevant passages", "no_answer: nothing relevant found"]
    assert reply.text == NO_ANSWER


def test_follow_up_questions_keep_the_conversation(knowledge: InMemoryKnowledgeBase) -> None:
    workflow = PolicyAssistantWorkflow(FakeChatModel(), InMemorySaver(), knowledge, TEST_MIN_SCORE)
    ask(workflow, "p3", "What happens to my pension when I change employer?")
    _, reply = ask(workflow, "p3", "Is the value transfer free of charge?")
    assert "(`value-transfer.md`)" in reply.text
    messages = workflow._graph.get_state({"configurable": {"thread_id": "p3"}}).values["messages"]
    assert len(messages) == 4  # two questions and two answers in the same thread
