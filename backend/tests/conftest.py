"""Shared fixtures: an app wired with SQLite in memory, an in-memory checkpointer, an in-memory
knowledge base (lexical test embeddings) and the fake LLM from tests/fakes."""

import os
from collections.abc import Iterator
from functools import cache
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

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
from app.rag.documents import load_chunks
from app.rag.embeddings import HashingEmbeddings
from app.rag.memory import InMemoryKnowledgeBase
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.container import Container
from app.workflows.registry import build_workflows
from tests.fakes.fake_llm import FakeChatModel

PASSWORD = "correct horse battery staple"
KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
TEST_MIN_SCORE = 0.1  # lexical test embeddings score lower than the real model


@cache
def shared_knowledge_base() -> InMemoryKnowledgeBase:
    """The real knowledge documents, embedded with the deterministic test embeddings (built once)."""
    knowledge = InMemoryKnowledgeBase(HashingEmbeddings(), HashingEmbeddings.model_name)
    knowledge.sync(load_chunks(KNOWLEDGE_DIR))
    return knowledge


@pytest.fixture
def knowledge() -> InMemoryKnowledgeBase:
    return shared_knowledge_base()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite://",
        jwt_secret=SecretStr("test-secret-that-is-at-least-32-characters-long"),
        demo_password=SecretStr(PASSWORD),
        mcp_allowed_hosts=["testserver"],
        rag_min_score=TEST_MIN_SCORE,
    )


def build_test_container(settings: Settings, llm: FakeChatModel | None = None) -> Container:
    """Same wiring as production, but SQLite in memory + InMemorySaver + in-memory knowledge + fake LLM."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    auth = AuthService(UserRepository(sessions), settings)
    auth.ensure_user(settings.demo_username, PASSWORD)
    workflows = build_workflows(
        llm or FakeChatModel(), InMemorySaver(), shared_knowledge_base(), settings.rag_min_score
    )
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
