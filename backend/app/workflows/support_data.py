"""Fictional backend systems for the support workflow: a member database and a policy knowledge base.

In production these would be a member-administration API and a vector-store retriever.
"""

from typing import Any

MEMBERS: dict[str, dict[str, Any]] = {
    "100234": {
        "name": "J. de Vries",
        "birth_year": 1962,
        "retirement_date": "2029-05-01",
        "accrued_pension_eur_per_year": 18450,
        "address": "Lindelaan 12, 3511 AB Utrecht",
    },
    "100871": {
        "name": "S. Bakker",
        "birth_year": 1975,
        "retirement_date": "2042-11-01",
        "accrued_pension_eur_per_year": 9120,
        "address": "Kade 4, 9711 BC Groningen",
    },
}

POLICIES = [
    "Retiring earlier: members may retire up to 10 years before the state pension age. "
    "The yearly pension is then lower because it is paid out for longer.",
    "Pension estimates: the online pension planner shows a personal estimate. "
    "A written estimate can be requested free of charge once per year.",
    "Address changes: the fund receives address changes automatically from the municipal "
    "register (BRP). Members living abroad must report changes themselves via the member portal.",
    "Partner pension: when a member dies, the registered partner receives a partner pension "
    "of 70% of the member's retirement pension.",
    "Complaints: complaints are handled by a senior employee within 6 weeks and are never answered automatically.",
]


def find_member(member_id: str | None) -> dict[str, Any] | None:
    """Look up a member by member number."""
    return MEMBERS.get(member_id or "")


def search_policies(query: str, k: int = 2) -> list[str]:
    """Naive keyword-overlap retrieval. In production: a vector store retriever."""
    words = {w.strip(".,!?").lower() for w in query.split() if len(w) > 3}
    return sorted(POLICIES, key=lambda p: -len(words & set(p.lower().split())))[:k]
