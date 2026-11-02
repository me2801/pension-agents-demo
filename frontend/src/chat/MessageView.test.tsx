import { render, screen } from "@testing-library/react";
import type { Message } from "../api/types";
import { MessageView } from "./MessageView";

function assistant(content: string): Message {
  return { id: "m1", role: "assistant", content, steps: [], choices: [], created_at: "2026-11-02T09:30:00Z" };
}

describe("MessageView", () => {
  it("renders Markdown tables as tables (LLMs answer comparisons with them)", () => {
    render(<MessageView message={assistant("| | Amsterdam |\n|---|---|\n| Temperature | 10.8 °C |")} />);

    const table = screen.getByRole("table");
    expect(screen.getByRole("columnheader", { name: "Amsterdam" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "10.8 °C" })).toBeInTheDocument();
    expect(table).not.toHaveTextContent("|---|");
  });

  it("never renders raw HTML from the model", () => {
    const { container } = render(<MessageView message={assistant('<img src="x" onerror="alert(1)">')} />);

    expect(container.querySelector("img")).toBeNull();
  });
});
