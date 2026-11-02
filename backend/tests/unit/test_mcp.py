"""The MCP layer: same services and same bearer tokens as the REST API."""

from typing import Any

from fastapi.testclient import TestClient

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(client: TestClient, headers: dict[str, str], method: str, params: dict[str, Any] | None = None) -> Any:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    response = client.post("/mcp", json=body, headers=MCP_HEADERS | headers)
    assert response.status_code == 200, response.text
    return response.json()["result"]


def call_tool(client: TestClient, headers: dict[str, str], name: str, **arguments: Any) -> Any:
    result = rpc(client, headers, "tools/call", {"name": name, "arguments": arguments})
    assert not result["isError"], result
    return result["structuredContent"]  # lists are wrapped as {"result": [...]}


def test_mcp_requires_a_bearer_token(client: TestClient) -> None:
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=MCP_HEADERS)
    assert response.status_code == 401


def test_mcp_lists_the_tools(client: TestClient, auth_headers: dict[str, str]) -> None:
    tools = {tool["name"] for tool in rpc(client, auth_headers, "tools/list")["tools"]}
    assert tools == {"list_workflows", "list_conversations", "send_message"}


def test_mcp_conversation_is_shared_with_the_rest_api(client: TestClient, auth_headers: dict[str, str]) -> None:
    workflows = call_tool(client, auth_headers, "list_workflows")
    assert {w["id"] for w in workflows["result"]} == {"weather", "support", "policy"}

    answer = call_tool(client, auth_headers, "send_message", workflow_id="support", message="Een klacht! Lid 100234")
    assert "never answered by AI" in answer["message"]["content"]
    final = call_tool(
        client,
        auth_headers,
        "send_message",
        workflow_id="support",
        message="Onze excuses.",
        conversation_id=answer["conversation_id"],
    )
    assert "Sent" in final["message"]["content"]

    rest_view = client.get("/api/v1/conversations", headers=auth_headers).json()
    assert [c["id"] for c in rest_view] == [answer["conversation_id"]]
    assert call_tool(client, auth_headers, "list_conversations")["result"][0]["id"] == answer["conversation_id"]
