/** Typed HTTP client for the backend. Components depend on the ChatApi interface, so tests can inject a fake. */
import createClient from "openapi-fetch";
import type { paths } from "./schema";
import { readEvents } from "./sse";
import type { ChatEvent, Conversation, Message, Token, WorkflowInfo } from "./types";

export interface ChatApi {
  listWorkflows(): Promise<WorkflowInfo[]>;
  listConversations(workflowId: string): Promise<Conversation[]>;
  startConversation(workflowId: string): Promise<Conversation>;
  getMessages(conversationId: string): Promise<Message[]>;
  sendMessage(conversationId: string, content: string, onEvent: (event: ChatEvent) => void): Promise<void>;
}

/** An HTTP error with the status code and the backend's message. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function detail(error: unknown, fallback: string): string {
  const value = (error as { detail?: unknown } | undefined)?.detail;
  return typeof value === "string" ? value : fallback;
}

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data === undefined) {
    throw new ApiError(result.response.status, detail(result.error, result.response.statusText));
  }
  return result.data;
}

/** Exchange username and password for an access token (OAuth2 password flow). */
export async function login(username: string, password: string): Promise<Token> {
  const client = createClient<paths>({ baseUrl: window.location.origin });
  return unwrap(
    await client.POST("/api/v1/auth/token", {
      body: { username, password, scope: "" },
      bodySerializer: (body) => new URLSearchParams(body as Record<string, string>),
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }),
  );
}

/** The real ChatApi, authenticated with a bearer token. Calls onUnauthorized on any 401. */
export class HttpChatApi implements ChatApi {
  private readonly client;

  constructor(
    private readonly token: string,
    private readonly onUnauthorized: () => void,
  ) {
    this.client = createClient<paths>({ baseUrl: window.location.origin, headers: this.headers() });
    this.client.use({
      onResponse: ({ response }) => {
        if (response.status === 401) this.onUnauthorized();
      },
    });
  }

  private headers(): Record<string, string> {
    return { Authorization: `Bearer ${this.token}` };
  }

  async listWorkflows(): Promise<WorkflowInfo[]> {
    return unwrap(await this.client.GET("/api/v1/workflows"));
  }

  async listConversations(workflowId: string): Promise<Conversation[]> {
    return unwrap(await this.client.GET("/api/v1/conversations", { params: { query: { workflow_id: workflowId } } }));
  }

  async startConversation(workflowId: string): Promise<Conversation> {
    return unwrap(await this.client.POST("/api/v1/conversations", { body: { workflow_id: workflowId } }));
  }

  async getMessages(conversationId: string): Promise<Message[]> {
    const path = { conversation_id: conversationId };
    return unwrap(await this.client.GET("/api/v1/conversations/{conversation_id}/messages", { params: { path } }));
  }

  /** Streams via fetch (EventSource can't POST or send headers). */
  async sendMessage(conversationId: string, content: string, onEvent: (event: ChatEvent) => void): Promise<void> {
    const response = await fetch(`/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      headers: { ...this.headers(), "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    if (response.status === 401) this.onUnauthorized();
    if (!response.ok || !response.body) throw new ApiError(response.status, response.statusText);
    for await (const event of readEvents(response.body)) onEvent(event);
  }
}
