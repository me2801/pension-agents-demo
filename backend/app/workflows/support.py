"""Pension fund support-email workflow: the features where LangGraph earns its place.

    START -> classify --complaint--> escalate (human writes reply) ------------------> send -> END
                |
                +--other--> lookup_member --+   (parallel fan-out / fan-in)
                |                           +--> draft_reply -> review --ok--> human_approval -> send
                +--other--> search_policy --+         ^           |                 |
                                                      +--revise---+                 +--> (revise / reject)

Shows: typed state with reducers, structured LLM output, branching, parallel nodes, a capped
self-correction loop, human-in-the-loop via interrupt(), and durable execution via the checkpointer.
All member data and policies are fictional.
"""

import operator
from collections.abc import Iterator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from app.domain.models import Reply, Step
from app.workflows.base import ChatWorkflow
from app.workflows.support_data import find_member, search_policies

MAX_REVISIONS = 2
APPROVAL_CHOICES = ["approve", "reject"]
ApprovalTarget = Literal["send", "draft_reply", "__end__"]


class State(TypedDict, total=False):
    """Graph state. `audit_log` has a reducer, so parallel nodes can both append to it."""

    email: str
    category: str
    member_id: str | None
    query_en: str
    member: dict[str, Any] | None
    policies: list[str]
    draft: str
    review_feedback: str
    revisions: int
    human_feedback: str
    status: str
    audit_log: Annotated[list[str], operator.add]


class Classification(BaseModel):
    """Structured output of the classifier."""

    category: Literal["pension_estimate", "address_change", "complaint", "other"]
    member_id: str | None = Field(description="Member number if mentioned, else null")
    query_en: str = Field(description="One-sentence English summary of the question")


class Review(BaseModel):
    """Structured output of the compliance reviewer."""

    approved: bool
    feedback: str = Field(description="What must change; empty if approved")


def _quote(text: str) -> str:
    """Render text as a Markdown blockquote."""
    return "\n".join(f"> {line}" for line in text.splitlines())


def _context(state: State) -> str:
    """The email, member data and policies, as prompt context."""
    member = state.get("member") or "Member not found - ask for the member number."
    policies = "\n".join(f"- {p}" for p in state.get("policies", []))
    return f"EMAIL:\n{state['email']}\n\nMEMBER DATA:\n{member}\n\nPOLICIES:\n{policies}"


def parse_decision(message: str, kind: str) -> dict[str, str] | None:
    """Turn a chat message into a resume value for a paused node; None if it needs more input."""
    text = message.strip()
    if kind == "escalation":
        return {"action": "edit", "text": text}
    command, separator, rest = text.partition(":")
    command, rest = command.strip().lower(), rest.strip()
    if command in ("approve", "reject") and not separator:
        return {"action": command}
    if command in ("edit", "revise") and separator:
        return {"action": command, "text": rest} if rest or command == "revise" else None
    return {"action": "revise", "text": text}  # free text = feedback for a rewrite


class SupportWorkflow(ChatWorkflow):
    """Classify, enrich, draft, review and - after human approval - send a reply to a member email."""

    id = "support"
    name = "Support email workflow"
    description = (
        "Paste a member's email. It is classified, enriched in parallel, drafted, checked by a "
        "reviewer LLM and only sent after you approve it. Complaints go straight to a human."
    )
    input_hint = "Paste an email from a member"
    examples = {
        "Retire earlier (NL)": (
            "Beste pensioenfonds, ik ben lid met nummer 100234. Ik overweeg om twee jaar eerder "
            "met pensioen te gaan. Wat betekent dat voor mijn pensioen? Groet, Jan de Vries"
        ),
        "Moved abroad (EN)": (
            "Hello, my member number is 100871. I recently moved to Antwerp, Belgium. "
            "Do I need to tell you my new address? Regards, Sanne Bakker"
        ),
        "Complaint (NL)": (
            "Dit is de derde keer dat ik bel en niemand helpt me! Mijn uitkering is te laat "
            "gestort. Lidnummer 100234. Ik wil een klacht indienen."
        ),
    }

    def __init__(self, llm: BaseChatModel, checkpointer: BaseCheckpointSaver[Any]):
        self._llm = llm
        self._classifier = llm.with_structured_output(Classification, method="json_schema")
        self._reviewer = llm.with_structured_output(Review, method="json_schema")
        self._graph = self._build_graph().compile(checkpointer=checkpointer)

    def _build_graph(self) -> StateGraph[State]:
        """Wire the nodes and edges."""
        builder = StateGraph(State)
        builder.add_node("classify", self._classify)
        builder.add_node("lookup_member", self._lookup_member)
        builder.add_node("search_policy", self._search_policy)
        builder.add_node("draft_reply", self._draft_reply)
        builder.add_node("review", self._review)
        builder.add_node("human_approval", self._human_approval)
        builder.add_node("escalate", self._escalate)
        builder.add_node("send", self._send)
        builder.add_edge(START, "classify")
        builder.add_conditional_edges(
            "classify", self._route_after_classify, ["escalate", "lookup_member", "search_policy"]
        )
        builder.add_edge(["lookup_member", "search_policy"], "draft_reply")  # fan-in: waits for both
        builder.add_edge("draft_reply", "review")
        builder.add_conditional_edges("review", self._route_after_review, ["draft_reply", "human_approval"])
        builder.add_edge("escalate", "send")
        builder.add_edge("send", END)
        # human_approval routes itself via Command(goto=...), so it needs no outgoing edges here.
        return builder

    # --- Nodes: each takes the state and returns only the keys it changes -------------------

    def _classify(self, state: State) -> dict[str, Any]:
        """Classify the email and extract the member number."""
        result = Classification.model_validate(
            self._classifier.invoke("Classify this email sent to a Dutch pension fund.\n\n" + state["email"])
        )
        return {
            "category": result.category,
            "member_id": result.member_id,
            "query_en": result.query_en,
            # Reset per-email fields: a thread can handle several emails in a row.
            "draft": "",
            "review_feedback": "",
            "human_feedback": "",
            "revisions": 0,
            "status": "",
            "audit_log": [f"classify: {result.category}, member {result.member_id}"],
        }

    @staticmethod
    def _route_after_classify(state: State) -> list[str] | str:
        """Complaints go to a human; everything else fans out to two lookups in parallel."""
        if state["category"] == "complaint":
            return "escalate"
        return ["lookup_member", "search_policy"]

    @staticmethod
    def _lookup_member(state: State) -> dict[str, Any]:
        """Fetch the member's data."""
        member = find_member(state.get("member_id"))
        return {"member": member, "audit_log": [f"lookup_member: {'found' if member else 'not found'}"]}

    @staticmethod
    def _search_policy(state: State) -> dict[str, Any]:
        """Retrieve the policies relevant to the question."""
        hits = search_policies(state["query_en"])
        return {"policies": hits, "audit_log": [f"search_policy: {len(hits)} snippets"]}

    def _draft_reply(self, state: State) -> dict[str, Any]:
        """Write (or rewrite) the reply, addressing reviewer and human feedback."""
        prompt = (
            "Write a reply to this email on behalf of the pension fund's member service.\n"
            "Reply in the same language as the email. Be warm, concise and factual. Use only "
            "the member data and policies below; never invent numbers or rules. "
            "Sign as 'Member Service'.\n\n" + _context(state)
        )
        feedback = "\n".join(f for f in (state.get("review_feedback"), state.get("human_feedback")) if f)
        if feedback:
            prompt += f"\n\nPREVIOUS DRAFT:\n{state['draft']}\n\nFEEDBACK TO ADDRESS:\n{feedback}"
        reason = "first draft"
        if state.get("human_feedback"):
            reason = "rewrite after human feedback"
        elif state.get("review_feedback"):
            reason = "rewrite after review"
        return {
            "draft": str(self._llm.invoke(prompt).text),
            # Only reviewer-triggered rewrites count towards MAX_REVISIONS.
            "revisions": state.get("revisions", 0) + (1 if state.get("review_feedback") else 0),
            "human_feedback": "",
            "audit_log": [f"draft_reply: {reason}"],
        }

    def _review(self, state: State) -> dict[str, Any]:
        """Let a second LLM check the draft for unsupported facts and promises."""
        result = Review.model_validate(
            self._reviewer.invoke(
                "You are a compliance reviewer at a pension fund. Check this draft reply. Reject it "
                "if it states facts not supported by the member data or policies, promises anything "
                "the fund cannot guarantee, or does not answer the question.\n\n"
                f"{_context(state)}\n\nDRAFT:\n{state['draft']}"
            )
        )
        return {
            "review_feedback": "" if result.approved else result.feedback,
            "audit_log": [f"review: {'approved' if result.approved else 'needs changes'}"],
        }

    @staticmethod
    def _route_after_review(state: State) -> str:
        """Loop back for a rewrite until approved or the revision cap is reached."""
        if state["review_feedback"] and state["revisions"] < MAX_REVISIONS:
            return "draft_reply"
        return "human_approval"

    # Nodes that pause for a human. On resume, LangGraph re-runs the node from the top and
    # interrupt() returns the human's answer - so keep code before interrupt() side-effect free.

    @staticmethod
    def _human_approval(state: State) -> Command[ApprovalTarget]:
        """Pause until a human approves, edits, asks for a revision or rejects the draft."""
        decision = interrupt(
            {"kind": "approval", "draft": state["draft"], "open_review_feedback": state.get("review_feedback")}
        )
        action, text = decision["action"], decision.get("text", "")
        routes: dict[str, tuple[ApprovalTarget, dict[str, Any]]] = {
            "approve": ("send", {}),
            "edit": ("send", {"draft": text}),
            "revise": ("draft_reply", {"human_feedback": text}),
            "reject": ("__end__", {"status": "rejected"}),  # "__end__" is LangGraph's END
        }
        goto, update = routes[action]
        return Command(goto=goto, update={**update, "audit_log": [f"human_approval: {action}"]})

    @staticmethod
    def _escalate(state: State) -> dict[str, Any]:
        """Pause until a human has written the reply to a complaint."""
        decision = interrupt({"kind": "escalation", "email": state["email"]})
        return {"draft": decision["text"], "audit_log": ["escalate: reply written by human"]}

    @staticmethod
    def _send(state: State) -> dict[str, Any]:
        """Send the reply. A real system would call the mail API here."""
        return {"status": "sent", "audit_log": ["send: reply sent"]}

    # --- ChatWorkflow interface --------------------------------------------------------------

    def stream(self, thread_id: str, message: str) -> Iterator[Step | Reply]:
        """Start a run for a new email, or resume a paused run with the human's decision."""
        config = RunnableConfig(configurable={"thread_id": thread_id})
        graph_input: Command[Any] | State = State(email=message)
        pending = self._pending(config)
        if pending is not None:
            decision = parse_decision(message, pending["kind"])
            if decision is None:
                yield Reply(text="Please put the replacement text after `edit:`.", choices=APPROVAL_CHOICES)
                return
            graph_input = Command(resume=decision)
        for update in self._graph.stream(graph_input, config, stream_mode="updates"):
            for node, payload in update.items():
                if node != "__interrupt__":
                    yield from (Step(text=entry) for entry in (payload or {}).get("audit_log", []))
        yield self._reply(config)

    def _pending(self, config: RunnableConfig) -> dict[str, Any] | None:
        """The value of the interrupt the graph is paused on, if any."""
        interrupts = self._graph.get_state(config).interrupts
        return dict(interrupts[0].value) if interrupts else None

    def _reply(self, config: RunnableConfig) -> Reply:
        """Describe the outcome of a run: waiting for a human, sent, or rejected."""
        pending = self._pending(config)
        if pending is not None:
            return self._pending_reply(pending)
        values = self._graph.get_state(config).values
        if values.get("status") == "sent":
            return Reply(text=f"✅ **Sent:**\n\n{_quote(values['draft'])}\n\nPaste another email to continue.")
        return Reply(text="❌ Rejected - nothing was sent. Paste another email to continue.")

    @staticmethod
    def _pending_reply(pending: dict[str, Any]) -> Reply:
        """Ask the human for the decision the graph is waiting on."""
        if pending["kind"] == "escalation":
            return Reply(text="**Complaint** - this is never answered by AI. Type the reply that should be sent.")
        text = f"**Draft reply** - approve before it is sent:\n\n{_quote(pending['draft'])}"
        if pending.get("open_review_feedback"):
            text += f"\n\n⚠️ The reviewer still has concerns: {pending['open_review_feedback']}"
        text += (
            "\n\nClick **approve** or **reject**, type `edit: <your text>` to send your own version, "
            "or just type feedback to get a rewrite."
        )
        return Reply(text=text, choices=APPROVAL_CHOICES)
