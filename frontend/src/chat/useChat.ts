/** All chat state for the page: workflows, the user's conversations and the open transcript. */
import { useCallback, useEffect, useState } from "react";
import type { ChatApi } from "../api/client";
import type { Conversation, WorkflowInfo } from "../api/types";
import { errorText, type Transcript, useTranscript } from "./useTranscript";

export interface ChatState extends Transcript {
  workflows: WorkflowInfo[];
  workflow: WorkflowInfo | undefined;
  conversations: Conversation[];
  error: string | null;
  dismissError: () => void;
  selectWorkflow: (workflowId: string) => void;
  sendMessage: (content: string) => Promise<void>;
}

/** Load the workflows once and select the first one. */
function useWorkflows(api: ChatApi, onSelect: (id: string) => void, onError: (message: string) => void) {
  const [workflows, setWorkflows] = useState<WorkflowInfo[]>([]);
  useEffect(() => {
    let active = true;
    api.listWorkflows().then(
      (list) => {
        if (!active || !list[0]) return;
        setWorkflows(list);
        onSelect(list[0].id);
      },
      (e: unknown) => {
        onError(errorText(e));
      },
    );
    return () => {
      active = false;
    };
  }, [api, onSelect, onError]);
  return workflows;
}

export function useChat(api: ChatApi): ChatState {
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const transcript = useTranscript(api, setError);
  const { reset, send } = transcript;

  const loadConversations = useCallback(
    (id: string) => {
      api.listConversations(id).then(setConversations, (e: unknown) => {
        setError(errorText(e));
      });
    },
    [api],
  );

  const selectWorkflow = useCallback(
    (id: string) => {
      setWorkflowId(id);
      reset();
      loadConversations(id);
    },
    [loadConversations, reset],
  );

  const workflows = useWorkflows(api, selectWorkflow, setError);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!workflowId) return;
      await send(workflowId, content);
      loadConversations(workflowId);
    },
    [workflowId, send, loadConversations],
  );

  const dismissError = useCallback(() => {
    setError(null);
  }, []);

  return {
    ...transcript,
    workflows,
    workflow: workflows.find((w) => w.id === workflowId),
    conversations,
    error,
    dismissError,
    selectWorkflow,
    sendMessage,
  };
}
