/** Workflow picker, conversation list and account actions. */
import type { Conversation, WorkflowInfo } from "../api/types";

interface Props {
  workflows: WorkflowInfo[];
  workflow: WorkflowInfo | undefined;
  conversations: Conversation[];
  conversationId: string | null;
  onSelectWorkflow: (id: string) => void;
  onNewConversation: () => void;
  onOpenConversation: (id: string) => void;
  onSignOut: () => void;
}

export function Sidebar(props: Props) {
  const { workflows, workflow, conversations, conversationId } = props;
  return (
    <aside className="sidebar">
      <label>
        Workflow
        <select value={workflow?.id ?? ""} onChange={(e) => { props.onSelectWorkflow(e.target.value); }}>
          {workflows.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
      </label>
      {workflow && <p className="description">{workflow.description}</p>}
      <button type="button" onClick={props.onNewConversation}>
        + New conversation
      </button>
      <h2>Conversations</h2>
      <nav aria-label="Conversations">
        {conversations.map((c) => (
          <button
            type="button"
            key={c.id}
            className={c.id === conversationId ? "conversation active" : "conversation"}
            aria-current={c.id === conversationId}
            onClick={() => { props.onOpenConversation(c.id); }}
          >
            {c.title}
          </button>
        ))}
      </nav>
      <button type="button" className="secondary" onClick={props.onSignOut}>
        Log out
      </button>
    </aside>
  );
}
