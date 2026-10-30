/** Buttons that send a prepared message: example prompts, or the choices a workflow offers. */

interface Props {
  replies: Record<string, string>; // button label -> message to send
  disabled: boolean;
  onSend: (message: string) => void;
}

export function QuickReplies({ replies, disabled, onSend }: Props) {
  const entries = Object.entries(replies);
  if (entries.length === 0) return null;
  return (
    <div className="quick-replies" role="group" aria-label="Quick replies">
      {entries.map(([label, message]) => (
        <button type="button" key={label} disabled={disabled} onClick={() => { onSend(message); }}>
          {label}
        </button>
      ))}
    </div>
  );
}
