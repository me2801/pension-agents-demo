/** The open conversation: its messages, and sending a message with live progress steps. */
import { useCallback, useState } from "react";
import type { ChatApi } from "../api/client";
import type { ChatEvent, Message } from "../api/types";

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export interface Transcript {
  conversationId: string | null;
  messages: Message[];
  liveSteps: string[];
  busy: boolean;
  reset: () => void;
  open: (conversationId: string) => Promise<void>;
  send: (workflowId: string, content: string) => Promise<void>;
}

export function useTranscript(api: ChatApi, onError: (message: string) => void): Transcript {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [liveSteps, setLiveSteps] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const reset = useCallback(() => {
    setConversationId(null);
    setMessages([]);
  }, []);

  const open = useCallback(
    async (id: string) => {
      setConversationId(id);
      setMessages(await api.getMessages(id));
    },
    [api],
  );

  const onEvent = useCallback((event: ChatEvent) => {
    if (event.type === "step") {
      setLiveSteps((steps) => [...steps, event.text]);
    } else {
      setLiveSteps([]);
      setMessages((current) => [...current, event.message]);
    }
  }, []);

  const send = useCallback(
    async (workflowId: string, content: string) => {
      setBusy(true);
      try {
        const id = conversationId ?? (await api.startConversation(workflowId)).id;
        setConversationId(id);
        await api.sendMessage(id, content, onEvent);
      } catch (error) {
        onError(errorText(error));
      } finally {
        setBusy(false);
        setLiveSteps([]);
      }
    },
    [api, conversationId, onEvent, onError],
  );

  return { conversationId, messages, liveSteps, busy, reset, open, send };
}
