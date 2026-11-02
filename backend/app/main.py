"""Composition root: builds the service container and the FastAPI app (REST + MCP).

Run locally:  uv run uvicorn app.main:create_app --factory --reload
"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models import BaseChatModel
from mcp.server.transport_security import TransportSecuritySettings

from app.api.errors import register_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.routes_auth import router as auth_router
from app.api.routes_chat import router as chat_router
from app.config import Settings, get_settings
from app.db.engine import create_postgres_checkpointer, create_sessions
from app.db.knowledge import create_knowledge_base
from app.db.repositories import ConversationRepository, UserRepository
from app.mcp.server import create_mcp_server
from app.observability import configure_tracing
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.container import Container
from app.workflows.registry import build_workflows, create_chat_model

logger = logging.getLogger(__name__)

API_DESCRIPTION = """
Chat with AI workflows. Authenticate via `POST /api/v1/auth/token` (or the **Authorize** button),
then start a conversation and send messages. Message responses are streamed as server-sent events.

The same functionality is available to AI clients over MCP at `/mcp` (same bearer token).
"""


def build_container(settings: Settings, chat_model: BaseChatModel | None = None) -> Container:
    """Wire repositories, workflows and services (dependency injection by hand, in one place).

    `chat_model` defaults to the configured production model; tests inject their own.
    """
    configure_tracing(settings.mlflow_tracking_uri, settings.mlflow_experiment)
    engine, sessions = create_sessions(settings.database_url)
    checkpointer, pool = create_postgres_checkpointer(settings.psycopg_url)
    knowledge = create_knowledge_base(settings, sessions)
    model_configured = chat_model is not None or settings.anthropic_api_key is not None
    if not model_configured:
        logger.warning("ANTHROPIC_API_KEY is not set: chats will answer that no AI model is configured")
    llm = chat_model or create_chat_model(settings)
    workflows = build_workflows(llm, checkpointer, knowledge, settings.rag_min_score)
    auth = AuthService(UserRepository(sessions), settings)
    if settings.demo_password is not None:
        auth.ensure_user(settings.demo_username, settings.demo_password.get_secret_value())
    chat = ChatService(ConversationRepository(sessions), workflows, model_configured)
    return Container(settings=settings, auth=auth, chat=chat, closers=[engine.dispose, pool.close])


def create_app(
    settings: Settings | None = None,
    container_factory: Callable[[Settings], Container] = build_container,
) -> FastAPI:
    """Create the app. Tests pass their own container_factory (e.g. SQLite + a fake LLM)."""
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    mcp = create_mcp_server(lambda: app.state.container, settings)
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=settings.mcp_allowed_hosts, allowed_origins=settings.cors_origins
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container_factory(settings)
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            app.state.container.close()

    app = FastAPI(title="Agent Chat API", version="1.0.0", description=API_DESCRIPTION, lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(chat_router)

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    def health() -> dict[str, str]:
        """Returns ok while the process is up."""
        return {"status": "ok"}

    app.mount("/", mcp_app)  # last: serves /mcp and the OAuth protected-resource metadata
    return app
