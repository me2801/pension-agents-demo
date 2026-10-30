"""Shared fixtures: an app wired with SQLite in memory, an in-memory checkpointer and the fake LLM."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.repositories import ConversationRepository, UserRepository
from app.db.tables import Base
from app.main import create_app
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.container import Container
from app.workflows.fake_llm import FakeChatModel
from app.workflows.registry import build_workflows

PASSWORD = "correct horse battery staple"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite://",
        jwt_secret=SecretStr("test-secret-that-is-at-least-32-characters-long"),
        llm_provider="fake",
        demo_password=SecretStr(PASSWORD),
        mcp_allowed_hosts=["testserver"],
    )


def build_test_container(settings: Settings, llm: FakeChatModel | None = None) -> Container:
    """Same wiring as production, but SQLite in memory + InMemorySaver + fake LLM."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    auth = AuthService(UserRepository(sessions), settings)
    auth.ensure_user(settings.demo_username, PASSWORD)
    workflows = build_workflows(llm or FakeChatModel(), InMemorySaver())
    chat = ChatService(ConversationRepository(sessions), workflows)
    return Container(settings=settings, auth=auth, chat=chat, closers=[engine.dispose])


@pytest.fixture
def container(settings: Settings) -> Iterator[Container]:
    container = build_test_container(settings)
    yield container
    container.close()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, container_factory=build_test_container)
    with TestClient(app) as client:  # `with` runs the lifespan (container + MCP session manager)
        yield client


@pytest.fixture
def token(client: TestClient, settings: Settings) -> str:
    response = client.post("/api/v1/auth/token", data={"username": settings.demo_username, "password": PASSWORD})
    assert response.status_code == 200
    access_token: str = response.json()["access_token"]
    return access_token


@pytest.fixture
def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
