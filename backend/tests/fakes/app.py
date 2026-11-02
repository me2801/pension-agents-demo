"""The production app with the scripted fake LLM injected, for end-to-end runs without an Anthropic key.

Only used by docker-compose.e2e.yml, which mounts tests/ into the backend container:
    uvicorn tests.fakes.app:create_fake_app --factory
"""

from functools import partial

from fastapi import FastAPI

from app.main import build_container, create_app
from tests.fakes.fake_llm import FakeChatModel


def create_fake_app() -> FastAPI:
    """Same wiring as production; only the chat model is replaced."""
    return create_app(container_factory=partial(build_container, chat_model=FakeChatModel()))
