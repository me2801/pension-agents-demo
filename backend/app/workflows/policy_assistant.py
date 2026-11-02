"""Policy assistant: retrieval-augmented answers from the fund's policy documents, with sources.

    START -> retrieve --(relevant passages?)--> generate -> END
                |
                +--(none)--> no_answer -> END

The model may only use the retrieved passages and must cite them; when retrieval finds nothing
relevant, the workflow says so without asking the model at all (no room for a made-up answer).
"""

import operator
from collections.abc import Iterator
from typing import Annotated, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph

from app.domain.models import Reply, Step
from app.rag.base import KnowledgeBase, Passage
from app.workflows.base import ChatWorkflow

TOP_K = 4
NO_ANSWER = (
    "I couldn't find this in the policy documents. Please contact Member Service, "
    "they can answer questions about your personal situation."
)
INSTRUCTIONS = (
    "You answer questions from members of a Dutch pension fund. Use ONLY the numbered sources "
    "below and cite them inline like [1] or [2]. If the sources don't answer the question, say so "
    "and suggest contacting Member Service; never guess. Answer in the language of the question, "
    "in a few short sentences.\n\nSOURCES:\n"
)


class State(MessagesState):
    """Conversation messages plus the passages retrieved for the current question."""

    passages: list[dict[str, Any]]
    audit_log: Annotated[list[str], operator.add]


def _sources_block(passages: list[Passage]) -> str:
    """Number the passages for the prompt."""
    return "\n\n".join(f"[{i}] {p.title}\n{p.text}" for i, p in enumerate(passages, start=1))


def _sources_footer(passages: list[Passage]) -> str:
    """The list of sources shown under the answer."""
    lines = [f"{i}. {p.title} (`{p.source}`)" for i, p in enumerate(passages, start=1)]
    return "\n\n**Sources**\n" + "\n".join(lines)


class PolicyAssistantWorkflow(ChatWorkflow):
    """Answers questions about the pension scheme from the policy documents (RAG)."""

    id = "policy"
    name = "Policy assistant"
    description = (
        "Ask anything about the pension scheme. Answers come only from the fund's policy documents "
        "(retrieval-augmented generation) and cite their sources; if the documents don't cover it, it says so."
    )
    input_hint = "Ask a question about the pension scheme"
    examples = {
        "Retire early?": "Can I retire before the state pension age, and what happens to my pension?",
        "Partner pension (NL)": "Hoeveel partnerpensioen krijgt mijn partner als ik overlijd?",
        "Changing jobs": "What happens to my pension when I change employer?",
    }

    def __init__(
        self,
        llm: BaseChatModel,
        checkpointer: BaseCheckpointSaver[Any],
        knowledge: KnowledgeBase,
        min_score: float,
    ):
        self._llm = llm
        self._knowledge = knowledge
        self._min_score = min_score
        builder = StateGraph(State)
        builder.add_node("retrieve", self._retrieve)
        builder.add_node("generate", self._generate)
        builder.add_node("no_answer", self._no_answer)
        builder.add_edge(START, "retrieve")
        builder.add_conditional_edges("retrieve", self._route, ["generate", "no_answer"])
        builder.add_edge("generate", END)
        builder.add_edge("no_answer", END)
        self._graph = builder.compile(checkpointer=checkpointer)

    def _retrieve(self, state: State) -> dict[str, Any]:
        """Find the passages most relevant to the latest question."""
        question = str(state["messages"][-1].text)
        hits = [p for p in self._knowledge.search(question, k=TOP_K) if p.score >= self._min_score]
        best = f", best match {hits[0].score:.2f}" if hits else ""
        return {
            "passages": [p.model_dump() for p in hits],
            "audit_log": [f"retrieve: {len(hits)} relevant passages{best}"],
        }

    @staticmethod
    def _route(state: State) -> str:
        """Only ask the model when there is something to ground the answer in."""
        return "generate" if state["passages"] else "no_answer"

    def _generate(self, state: State) -> dict[str, Any]:
        """Answer from the passages, with the conversation so far for follow-up questions."""
        passages = [Passage.model_validate(p) for p in state["passages"]]
        prompt = [SystemMessage(INSTRUCTIONS + _sources_block(passages)), *state["messages"]]
        answer = self._llm.invoke(prompt)
        return {"messages": [answer], "audit_log": [f"generate: answer from {len(passages)} sources"]}

    @staticmethod
    def _no_answer(state: State) -> dict[str, Any]:
        """Decline instead of guessing."""
        return {"messages": [AIMessage(NO_ANSWER)], "audit_log": ["no_answer: nothing relevant found"]}

    def stream(self, thread_id: str, message: str) -> Iterator[Step | Reply]:
        """Retrieve, answer and list the sources used."""
        config = RunnableConfig(configurable={"thread_id": thread_id})
        graph_input = State(messages=[HumanMessage(message)], passages=[], audit_log=[])
        for update in self._graph.stream(graph_input, config, stream_mode="updates"):
            for payload in update.values():
                yield from (Step(text=entry) for entry in payload.get("audit_log", []))
        values = self._graph.get_state(config).values
        passages = [Passage.model_validate(p) for p in values["passages"]]
        answer = str(values["messages"][-1].text)
        yield Reply(text=answer + (_sources_footer(passages) if passages else ""))
