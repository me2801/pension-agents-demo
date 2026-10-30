"""The support workflow, driven through the ChatWorkflow interface."""

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.domain.models import Reply, Step
from app.workflows.fake_llm import FakeChatModel
from app.workflows.support import SupportWorkflow, parse_decision

EMAIL = SupportWorkflow.examples["Retire earlier (NL)"]
COMPLAINT = SupportWorkflow.examples["Complaint (NL)"]


def turn(workflow: SupportWorkflow, thread: str, message: str) -> tuple[list[str], Reply]:
    events = list(workflow.stream(thread, message))
    *steps, reply = events
    assert isinstance(reply, Reply)
    assert all(isinstance(step, Step) for step in steps)
    return [step.text for step in steps if isinstance(step, Step)], reply


@pytest.fixture
def workflow() -> SupportWorkflow:
    return SupportWorkflow(FakeChatModel(review_rejections=1), InMemorySaver())


def test_email_is_drafted_reviewed_and_waits_for_approval(workflow: SupportWorkflow) -> None:
    steps, reply = turn(workflow, "t1", EMAIL)
    assert steps == [
        "classify: other, member 100234",
        "lookup_member: found",
        "search_policy: 2 snippets",
        "draft_reply: first draft",
        "review: needs changes",
        "draft_reply: rewrite after review",
        "review: approved",
    ]
    assert reply.choices == ["approve", "reject"]
    assert "(revised)" in reply.text


def test_approve_sends_the_draft(workflow: SupportWorkflow) -> None:
    turn(workflow, "t1", EMAIL)
    steps, reply = turn(workflow, "t1", "approve")
    assert steps == ["human_approval: approve", "send: reply sent"]
    assert "Sent" in reply.text
    assert reply.choices == []


def test_free_text_asks_for_a_rewrite(workflow: SupportWorkflow) -> None:
    turn(workflow, "t1", EMAIL)
    steps, reply = turn(workflow, "t1", "Mention the online planner")
    assert steps[:2] == ["human_approval: revise", "draft_reply: rewrite after human feedback"]
    assert reply.choices == ["approve", "reject"]


def test_edit_sends_the_human_text(workflow: SupportWorkflow) -> None:
    turn(workflow, "t1", EMAIL)
    _, reply = turn(workflow, "t1", "edit: My own reply")
    assert "> My own reply" in reply.text


def test_empty_edit_keeps_waiting(workflow: SupportWorkflow) -> None:
    turn(workflow, "t1", EMAIL)
    steps, reply = turn(workflow, "t1", "edit:")
    assert steps == []
    assert "replacement text" in reply.text
    _, reply = turn(workflow, "t1", "approve")  # still paused, so approve works
    assert "Sent" in reply.text


def test_reject_sends_nothing_and_next_email_starts_fresh(workflow: SupportWorkflow) -> None:
    turn(workflow, "t1", EMAIL)
    _, reply = turn(workflow, "t1", "reject")
    assert "Rejected" in reply.text
    steps, _ = turn(workflow, "t1", EMAIL)
    assert "draft_reply: first draft" in steps  # previous feedback was reset


def test_complaint_is_escalated_to_a_human() -> None:
    workflow = SupportWorkflow(FakeChatModel(), InMemorySaver())
    steps, reply = turn(workflow, "t2", COMPLAINT)
    assert steps == ["classify: complaint, member 100234"]
    assert reply.choices == []
    steps, reply = turn(workflow, "t2", "Beste heer De Vries, onze excuses.")
    assert steps == ["escalate: reply written by human", "send: reply sent"]
    assert "onze excuses" in reply.text


def test_reviewer_concerns_are_shown_when_the_revision_cap_is_hit() -> None:
    workflow = SupportWorkflow(FakeChatModel(review_rejections=99), InMemorySaver())
    steps, reply = turn(workflow, "t3", EMAIL)
    assert steps.count("review: needs changes") == 3  # first draft + MAX_REVISIONS rewrites
    assert "reviewer still has concerns" in reply.text


@pytest.mark.parametrize(
    ("message", "kind", "expected"),
    [
        ("approve", "approval", {"action": "approve"}),
        (" Reject ", "approval", {"action": "reject"}),
        ("edit: new text", "approval", {"action": "edit", "text": "new text"}),
        ("edit:", "approval", None),
        ("revise:", "approval", {"action": "revise", "text": ""}),
        ("please be shorter", "approval", {"action": "revise", "text": "please be shorter"}),
        ("approve: but shorter", "approval", {"action": "revise", "text": "approve: but shorter"}),
        ("any reply text", "escalation", {"action": "edit", "text": "any reply text"}),
    ],
)
def test_parse_decision(message: str, kind: str, expected: dict[str, str] | None) -> None:
    assert parse_decision(message, kind) == expected
