"""Against a real Postgres (Testcontainers): migrations, production wiring and durable execution."""

import json
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect
from testcontainers.postgres import PostgresContainer

from app.config import Settings
from app.main import create_app
from app.workflows.support import SupportWorkflow

pytestmark = pytest.mark.integration
PASSWORD = "integration-test-password"


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
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
        llm_provider="fake",
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
    assert {"users", "conversations", "messages"} <= set(inspect(engine).get_table_names())
    command.downgrade(alembic_config(settings.database_url), "base")
    assert "conversations" not in inspect(engine).get_table_names()
    command.upgrade(alembic_config(settings.database_url), "head")
    engine.dispose()


def test_a_paused_approval_survives_a_restart(settings: Settings) -> None:
    with TestClient(create_app(settings)) as first_run:  # production wiring: build_container
        headers = login(first_run)
        conversation_id = first_run.post("/api/v1/conversations", json={"workflow_id": "support"}, headers=headers)
        conversation_id = conversation_id.json()["id"]
        paused = last_event(first_run, headers, conversation_id, SupportWorkflow.examples["Retire earlier (NL)"])
        assert paused["message"]["choices"] == ["approve", "reject"]  # type: ignore[index]

    # A brand-new app (fresh process state); only Postgres remembers the paused graph.
    with TestClient(create_app(settings)) as second_run:
        headers = login(second_run)
        done = last_event(second_run, headers, conversation_id, "approve")
        assert "Sent" in done["message"]["content"]  # type: ignore[index]
        history = second_run.get(f"/api/v1/conversations/{conversation_id}/messages", headers=headers).json()
        assert len(history) == 4
