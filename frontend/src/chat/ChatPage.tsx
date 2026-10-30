/** The chat screen. It only knows the ChatApi interface and the workflows the backend lists. */
import { useEffect, useRef } from "react";
import type { ChatApi } from "../api/client";
import type { Message } from "../api/types";
import { Composer } from "./Composer";
import { MessageView, StepList } from "./MessageView";
import { QuickReplies } from "./QuickReplies";
import { Sidebar } from "./Sidebar";
import { type ChatState, useChat } from "./useChat";

interface Props {
  api: ChatApi;
  onSignOut: () => void;
}

/** Example prompts in an empty chat, otherwise the choices of the last answer. */
export function quickReplies(messages: Message[], examples: Record<string, string>): Record<string, string> {
  const last = messages.at(-1);
  if (!last) return examples;
  if (last.role !== "assistant") return {};
  return Object.fromEntries(last.choices.map((choice) => [choice, choice]));
}

function Transcript({ messages, liveSteps, busy }: Pick<ChatState, "messages" | "liveSteps" | "busy">) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, liveSteps]);

  return (
    <section className="messages" aria-live="polite">
      {messages.map((m) => (
        <MessageView key={m.id} message={m} />
      ))}
      {busy && (
        <div className="message assistant working" aria-label="Working">
          <p>Working...</p>
          <StepList steps={liveSteps} />
        </div>
      )}
      <div ref={bottom} />
    </section>
  );
}

function ErrorBanner({ error, onDismiss }: { error: string | null; onDismiss: () => void }) {
  if (!error) return null;
  return (
    <p role="alert" className="error">
      {error}{" "}
      <button type="button" onClick={onDismiss}>
        Dismiss
      </button>
    </p>
  );
}

function ChatMain({ chat }: { chat: ChatState }) {
  const send = (message: string) => void chat.sendMessage(message);
  const workflow = chat.workflow;
  return (
    <main className="chat">
      <h1>{workflow?.name ?? "Agent Chat"}</h1>
      <ErrorBanner error={chat.error} onDismiss={chat.dismissError} />
      <Transcript messages={chat.messages} liveSteps={chat.liveSteps} busy={chat.busy} />
      <QuickReplies replies={quickReplies(chat.messages, workflow?.examples ?? {})} disabled={chat.busy} onSend={send} />
      <Composer placeholder={workflow?.input_hint ?? ""} disabled={chat.busy || !workflow} onSend={send} />
    </main>
  );
}

export function ChatPage({ api, onSignOut }: Props) {
  const chat = useChat(api);
  return (
    <div className="layout">
      <Sidebar
        workflows={chat.workflows}
        workflow={chat.workflow}
        conversations={chat.conversations}
        conversationId={chat.conversationId}
        onSelectWorkflow={chat.selectWorkflow}
        onNewConversation={chat.reset}
        onOpenConversation={(id) => void chat.open(id)}
        onSignOut={onSignOut}
      />
      <ChatMain chat={chat} />
    </div>
  );
}
