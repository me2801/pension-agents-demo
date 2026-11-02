/** One chat message. Markdown is rendered by react-markdown, which never renders raw HTML (no XSS). */
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../api/types";

/** GitHub-flavoured Markdown (tables, strikethrough, task lists): what LLMs actually write. */
function Md({ children }: { children: string }) {
  return <Markdown remarkPlugins={[remarkGfm]}>{children}</Markdown>;
}

export function StepList({ steps }: { steps: string[] }) {
  return (
    <ul className="steps">
      {steps.map((step, i) => (
        <li key={i}>
          <Md>{step}</Md>
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
      <Md>{message.content}</Md>
    </article>
  );
}
