"""Against a real Postgres (Testcontainers): migrations, production wiring and durable execution."""

import json
from collections.abc import Iterator
from functools import partial

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect
from testcontainers.postgres import PostgresContainer

from app.cli import ingest
from app.config import Settings
from app.db.engine import create_sessions
from app.db.knowledge import create_knowledge_base
from app.main import build_container, create_app
from app.workflows.support import SupportWorkflow
from tests.fakes.fake_llm import FakeChatModel

pytestmark = pytest.mark.integration
PASSWORD = "integration-test-password"


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("pgvector/pgvector:pg17", driver="psycopg") as postgres:
        url: str = postgres.get_connection_url()
        yield url


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="module")
def settings(database_url: str) -> Settings:
    command.upgrade(alembic_config(database_url), "head")
    return Settings(
        environment="test",
        database_url=database_url,
        jwt_secret=SecretStr("integration-secret-that-is-at-least-32-chars"),
        demo_password=SecretStr(PASSWORD),
        mcp_allowed_hosts=["testserver"],
    )


def login(client: TestClient) -> dict[str, str]:
    token = client.post("/api/v1/auth/token", data={"username": "demo", "password": PASSWORD}).json()
    return {"Authorization": f"Bearer {token['access_token']}"}


def last_event(client: TestClient, headers: dict[str, str], conversation_id: str, content: str) -> dict[str, object]:
    url = f"/api/v1/conversations/{conversation_id}/messages"
    lines = client.post(url, json={"content": content}, headers=headers).text.splitlines()
    event: dict[str, object] = json.loads([line for line in lines if line.startswith("data: ")][-1][6:])
    return event


def test_migrations_create_the_schema_and_downgrade_cleanly(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    assert {"users", "conversations", "messages", "knowledge_chunks"} <= set(inspect(engine).get_table_names())
    command.downgrade(alembic_config(settings.database_url), "base")
    assert "conversations" not in inspect(engine).get_table_names()
    command.upgrade(alembic_config(settings.database_url), "head")
    engine.dispose()


def production_app(settings: Settings) -> FastAPI:
    """Production wiring (build_container) with the fake LLM injected."""
    return create_app(settings, partial(build_container, chat_model=FakeChatModel()))


def test_a_paused_approval_survives_a_restart(settings: Settings) -> None:
    with TestClient(production_app(settings)) as first_run:
        headers = login(first_run)
        conversation_id = first_run.post("/api/v1/conversations", json={"workflow_id": "support"}, headers=headers)
        conversation_id = conversation_id.json()["id"]
        paused = last_event(first_run, headers, conversation_id, SupportWorkflow.examples["Retire earlier (NL)"])
        assert paused["message"]["choices"] == ["approve", "reject"]  # type: ignore[index]

    # A brand-new app (fresh process state); only Postgres remembers the paused graph.
    with TestClient(production_app(settings)) as second_run:
        headers = login(second_run)
        done = last_event(second_run, headers, conversation_id, "approve")
        assert "Sent" in done["message"]["content"]  # type: ignore[index]
        history = second_run.get(f"/api/v1/conversations/{conversation_id}/messages", headers=headers).json()
        assert len(history) == 4


def test_ingest_is_idempotent_and_search_finds_the_right_document(settings: Settings) -> None:
    first = ingest(settings)  # the real local embedding model, the real pgvector table
    assert first.added > 0
    assert ingest(settings).model_dump() == {"added": 0, "removed": 0, "unchanged": first.added}

    engine, sessions = create_sessions(settings.database_url)
    hits = create_knowledge_base(settings, sessions).search("Hoeveel partnerpensioen krijgt mijn partner?", k=3)
    engine.dispose()
    assert hits[0].source == "partner-pension.md"  # a Dutch question finds the English document
    assert hits[0].score > hits[-1].score
