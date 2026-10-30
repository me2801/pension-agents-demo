"""The REST layer: auth, routing, status codes and the SSE stream."""

import json
from typing import Any

from fastapi.testclient import TestClient

from app.workflows.support import SupportWorkflow


def sse_events(body: str) -> list[dict[str, Any]]:
    return [json.loads(line.removeprefix("data: ")) for line in body.splitlines() if line.startswith("data: ")]


def start(client: TestClient, headers: dict[str, str], workflow_id: str = "support") -> str:
    response = client.post("/api/v1/conversations", json={"workflow_id": workflow_id}, headers=headers)
    assert response.status_code == 201
    conversation_id: str = response.json()["id"]
    return conversation_id


def send(client: TestClient, headers: dict[str, str], conversation_id: str, content: str) -> list[dict[str, Any]]:
    url = f"/api/v1/conversations/{conversation_id}/messages"
    response = client.post(url, json={"content": content}, headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return sse_events(response.text)


def test_health_needs_no_auth(client: TestClient) -> None:
    response = client.get("/health")
    assert response.json() == {"status": "ok"}
    assert "X-Request-ID" in response.headers


def test_everything_else_needs_a_valid_token(client: TestClient) -> None:
    assert client.get("/api/v1/workflows").status_code == 401
    response = client.get("/api/v1/workflows", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_password_is_401(client: TestClient) -> None:
    response = client.post("/api/v1/auth/token", data={"username": "demo", "password": "nope"})
    assert response.status_code == 401


def test_me_and_workflows(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/v1/auth/me", headers=auth_headers).json()["username"] == "demo"
    workflows = client.get("/api/v1/workflows", headers=auth_headers).json()
    assert [w["id"] for w in workflows] == ["weather", "support"]


def test_full_support_flow_over_http(client: TestClient, auth_headers: dict[str, str]) -> None:
    conversation_id = start(client, auth_headers)
    events = send(client, auth_headers, conversation_id, SupportWorkflow.examples["Moved abroad (EN)"])
    assert events[0]["type"] == "started"
    assert {e["type"] for e in events[1:-1]} == {"step"}
    assert events[-1]["type"] == "done"
    assert events[-1]["message"]["choices"] == ["approve", "reject"]

    events = send(client, auth_headers, conversation_id, "approve")
    assert "Sent" in events[-1]["message"]["content"]

    messages = client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=auth_headers).json()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    conversations = client.get("/api/v1/conversations?workflow_id=support", headers=auth_headers).json()
    assert conversations[0]["title"].startswith("Hello, my member number")


def test_unknown_conversation_is_404_before_streaming(client: TestClient, auth_headers: dict[str, str]) -> None:
    url = "/api/v1/conversations/00000000-0000-4000-8000-000000000000/messages"
    assert client.post(url, json={"content": "hi"}, headers=auth_headers).status_code == 404
    assert client.get(url, headers=auth_headers).status_code == 404


def test_validation_errors(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.post("/api/v1/conversations", json={"workflow_id": "nope"}, headers=auth_headers).status_code == 422
    conversation_id = start(client, auth_headers)
    url = f"/api/v1/conversations/{conversation_id}/messages"
    assert client.post(url, json={"content": ""}, headers=auth_headers).status_code == 422


def test_openapi_documents_the_models(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    for model in ("Conversation", "Message", "WorkflowInfo", "ChatEventSchema", "Token"):
        assert model in spec["components"]["schemas"]
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
