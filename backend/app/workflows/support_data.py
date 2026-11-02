"""Fictional member administration for the support workflow (a member-administration API in production)."""

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


def find_member(member_id: str | None) -> dict[str, Any] | None:
    """Look up a member by member number."""
    return MEMBERS.get(member_id or "")
