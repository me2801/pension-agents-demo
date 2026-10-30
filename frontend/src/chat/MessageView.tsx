/** One chat message. Markdown is rendered by react-markdown, which never renders raw HTML (no XSS). */
import Markdown from "react-markdown";
import type { Message } from "../api/types";

export function StepList({ steps }: { steps: string[] }) {
  return (
    <ul className="steps">
      {steps.map((step, i) => (
        <li key={i}>
          <Markdown>{step}</Markdown>
        </li>
      ))}
    </ul>
  );
}

export function MessageView({ message }: { message: Message }) {
  return (
    <article className={`message ${message.role}`} aria-label={`${message.role} message`}>
      {message.steps.length > 0 && (
        <details>
          <summary>{message.steps.length} steps</summary>
          <StepList steps={message.steps} />
        </details>
      )}
      <Markdown>{message.content}</Markdown>
    </article>
  );
}
