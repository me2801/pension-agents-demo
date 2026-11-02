"""API-level end-to-end tests against the full running stack (through nginx), with the scripted fake model.

Start the stack with docker-compose.e2e.yml (see the README), then run:
    E2E_BASE_URL=http://localhost:8080 E2E_PASSWORD=... uv run pytest -m e2e
"""

import json
import os
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def http() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=os.environ.get("E2E_BASE_URL", "http://localhost:8080"), timeout=60) as client:
        token = client.post(
            "/api/v1/auth/token", data={"username": "demo", "password": os.environ["E2E_PASSWORD"]}
        ).json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        yield client


def chat(http: httpx.Client, conversation_id: str, content: str) -> dict[str, Any]:
    response = http.post(f"/api/v1/conversations/{conversation_id}/messages", json={"content": content})
    response.raise_for_status()
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[-1]["type"] == "done"
    message: dict[str, Any] = events[-1]["message"]
    return message


def test_support_flow_through_the_proxy(http: httpx.Client) -> None:
    conversation_id = http.post("/api/v1/conversations", json={"workflow_id": "support"}).json()["id"]
    draft = chat(http, conversation_id, "Hello, my member number is 100871. Do I need to report my new address?")
    assert draft["choices"] == ["approve", "reject"]
    assert "Sent" in chat(http, conversation_id, "approve")["content"]


def test_mcp_through_the_proxy(http: httpx.Client) -> None:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_workflows", "arguments": {}}}
    response = http.post("/mcp", json=body, headers={"Accept": "application/json, text/event-stream"})
    response.raise_for_status()
    workflows = response.json()["result"]["structuredContent"]["result"]
    assert {w["id"] for w in workflows} == {"weather", "support", "policy"}


def test_requests_without_a_token_are_refused() -> None:
    base_url = os.environ.get("E2E_BASE_URL", "http://localhost:8080")
    assert httpx.get(f"{base_url}/api/v1/workflows").status_code == 401
    assert httpx.post(f"{base_url}/mcp", json={}).status_code == 401
