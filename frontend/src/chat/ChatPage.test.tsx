import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChatApi } from "../api/client";
import type { ChatEvent, Conversation, Message, WorkflowInfo } from "../api/types";
import { ChatPage } from "./ChatPage";

const WORKFLOWS: WorkflowInfo[] = [
  { id: "support", name: "Support", description: "Drafts replies", input_hint: "Paste an email", examples: { Example: "Hi" } },
  { id: "weather", name: "Weather", description: "Weather agent", input_hint: "Ask", examples: {} },
];

function message(role: Message["role"], content: string, choices: string[] = []): Message {
  return { id: crypto.randomUUID(), role, content, steps: [], choices, created_at: "2026-10-30T12:00:00Z" };
}

function conversation(id: string, title: string): Conversation {
  return { id, workflow_id: "support", title, created_at: "", updated_at: "" };
}

/** A fake backend: answers every message with a draft and approve/reject, and "approve" with "Sent". */
function fakeApi(overrides: Partial<ChatApi> = {}): ChatApi {
  return {
    listWorkflows: vi.fn(() => Promise.resolve(WORKFLOWS)),
    listConversations: vi.fn(() => Promise.resolve([conversation("old", "Earlier chat")])),
    startConversation: vi.fn(() => Promise.resolve(conversation("new", "New conversation"))),
    getMessages: vi.fn(() => Promise.resolve([message("user", "earlier question"), message("assistant", "earlier answer")])),
    sendMessage: vi.fn((_id: string, content: string, onEvent: (e: ChatEvent) => void) => {
      onEvent({ type: "started", message: message("user", content) });
      onEvent({ type: "step", text: "classify" });
      const reply = content === "approve" ? message("assistant", "Sent!") : message("assistant", "**Draft**", ["approve", "reject"]);
      onEvent({ type: "done", message: reply });
      return Promise.resolve();
    }),
    ...overrides,
  };
}

describe("ChatPage", () => {
  it("runs a conversation with quick replies", async () => {
    const api = fakeApi();
    render(<ChatPage api={api} onSignOut={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Example" }));

    expect(api.startConversation).toHaveBeenCalledWith("support");
    expect(await screen.findByText("Draft")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "approve" }));
    expect(await screen.findByText("Sent!")).toBeInTheDocument();
    expect(api.sendMessage).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "approve" })).not.toBeInTheDocument();
  });

  it("sends typed messages with Enter", async () => {
    const api = fakeApi();
    render(<ChatPage api={api} onSignOut={vi.fn()} />);
    const input = await screen.findByPlaceholderText("Paste an email");
    await userEvent.type(input, "line one{Shift>}{Enter}{/Shift}line two{Enter}");
    expect(api.sendMessage).toHaveBeenCalledWith("new", "line one\nline two", expect.any(Function));
  });

  it("opens an earlier conversation and switches workflows", async () => {
    const api = fakeApi();
    render(<ChatPage api={api} onSignOut={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Earlier chat" }));
    expect(await screen.findByText("earlier answer")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByRole("combobox"), "weather");
    expect(api.listConversations).toHaveBeenLastCalledWith("weather");
    expect(screen.queryByText("earlier answer")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Weather" })).toBeInTheDocument();
  });

  it("shows errors and lets the user dismiss them", async () => {
    const api = fakeApi({ sendMessage: vi.fn(() => Promise.reject(new Error("Network down"))) });
    render(<ChatPage api={api} onSignOut={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Example" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Network down");
    await userEvent.click(within(alert).getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reports a failure to load workflows", async () => {
    render(<ChatPage api={fakeApi({ listWorkflows: () => Promise.reject(new Error("Unauthorized")) })} onSignOut={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unauthorized");
  });

  it("signs out", async () => {
    const onSignOut = vi.fn();
    render(<ChatPage api={fakeApi()} onSignOut={onSignOut} />);
    await userEvent.click(await screen.findByRole("button", { name: "Log out" }));
    expect(onSignOut).toHaveBeenCalledOnce();
  });
});
