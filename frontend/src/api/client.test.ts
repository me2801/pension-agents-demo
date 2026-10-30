import { ApiError, HttpChatApi, login } from "./client";
import type { ChatEvent } from "./types";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function lastRequest(): Request {
  const call = fetchMock.mock.calls.at(-1);
  if (!call) throw new Error("fetch was not called");
  return call[0] instanceof Request ? call[0] : new Request(String(call[0]), call[1]);
}

describe("login", () => {
  it("posts the OAuth2 password form", async () => {
    fetchMock.mockResolvedValue(json({ access_token: "t", token_type: "bearer", expires_in: 60 }));
    expect((await login("demo", "pw")).access_token).toBe("t");
    const request = lastRequest();
    expect(request.headers.get("Content-Type")).toBe("application/x-www-form-urlencoded");
    const body = await request.text();
    expect(new URLSearchParams(body).get("username")).toBe("demo");
  });

  it("throws the backend's message on failure", async () => {
    fetchMock.mockResolvedValue(json({ detail: "Invalid username or password" }, 401));
    await expect(login("demo", "bad")).rejects.toEqual(new ApiError(401, "Invalid username or password"));
  });
});

describe("HttpChatApi", () => {
  it("sends the bearer token", async () => {
    fetchMock.mockResolvedValue(json([]));
    await new HttpChatApi("secret", vi.fn()).listWorkflows();
    expect(lastRequest().headers.get("Authorization")).toBe("Bearer secret");
  });

  it("reports a 401 so the app can log out", async () => {
    fetchMock.mockResolvedValue(json({ detail: "Invalid or expired token" }, 401));
    const onUnauthorized = vi.fn();
    await expect(new HttpChatApi("old", onUnauthorized).listConversations("support")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("starts conversations and reads messages", async () => {
    const api = new HttpChatApi("t", vi.fn());
    fetchMock.mockResolvedValueOnce(json({ id: "c1" }, 201));
    expect((await api.startConversation("support")).id).toBe("c1");
    fetchMock.mockResolvedValueOnce(json([{ id: "m1" }]));
    expect(await api.getMessages("c1")).toEqual([{ id: "m1" }]);
    expect(lastRequest().url).toContain("/api/v1/conversations/c1/messages");
  });

  it("streams message events", async () => {
    const body = 'data: {"type":"step","text":"thinking"}\n\n';
    fetchMock.mockResolvedValue(new Response(body, { headers: { "Content-Type": "text/event-stream" } }));
    const events: ChatEvent[] = [];
    await new HttpChatApi("t", vi.fn()).sendMessage("c1", "hi", (e) => events.push(e));
    expect(events).toEqual([{ type: "step", text: "thinking" }]);
  });

  it("fails a stream request with an ApiError", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 404, statusText: "Not Found" }));
    await expect(new HttpChatApi("t", vi.fn()).sendMessage("nope", "hi", vi.fn())).rejects.toEqual(
      new ApiError(404, "Not Found"),
    );
  });
});
