/** The message input. Enter sends, Shift+Enter adds a new line. */
import { type KeyboardEvent, type SyntheticEvent, useState } from "react";

interface Props {
  placeholder: string;
  disabled: boolean;
  onSend: (message: string) => void;
}

export function Composer({ placeholder, disabled, onSend }: Props) {
  const [text, setText] = useState("");

  const submit = (event?: SyntheticEvent) => {
    event?.preventDefault();
    const message = text.trim();
    if (!message || disabled) return;
    onSend(message);
    setText("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) submit(event);
  };

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        aria-label="Message"
        value={text}
        placeholder={placeholder}
        rows={2}
        onChange={(e) => { setText(e.target.value); }}
        onKeyDown={onKeyDown}
      />
      <button type="submit" disabled={disabled || !text.trim()}>
        Send
      </button>
    </form>
  );
}
