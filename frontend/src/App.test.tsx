import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** A tiny fake backend for the auth flow. */
function backend(input: RequestInfo | URL): Promise<Response> {
  const url = input instanceof Request ? input.url : String(input);
  if (url.endsWith("/auth/token")) return Promise.resolve(json({ access_token: "t", token_type: "bearer", expires_in: 60 }));
  if (url.includes("/workflows")) return Promise.resolve(json([]));
  return Promise.resolve(json([]));
}

beforeEach(() => {
  sessionStorage.clear();
  vi.stubGlobal("fetch", vi.fn(backend));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function logIn(password = "pw") {
  await userEvent.type(screen.getByLabelText("Username"), "demo");
  await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
}

describe("App", () => {
  it("logs in, keeps the token for this tab, and logs out", async () => {
    render(<App />);
    await logIn();
    expect(await screen.findByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(sessionStorage.getItem("agent-chat-token")).toBe("t");

    await userEvent.click(screen.getByRole("button", { name: "Log out" }));
    expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
    expect(sessionStorage.getItem("agent-chat-token")).toBeNull();
  });

  it("shows a login error", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ detail: "Invalid username or password" }, 401))));
    render(<App />);
    await logIn("wrong");
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
    expect(screen.getByRole("button", { name: "Log in" })).toBeEnabled();
  });

  it("starts in the chat when a token is stored", async () => {
    sessionStorage.setItem("agent-chat-token", "t");
    render(<App />);
    expect(await screen.findByRole("button", { name: "Log out" })).toBeInTheDocument();
  });
});
