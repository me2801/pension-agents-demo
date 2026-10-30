/** Username/password login form. */
import { type SyntheticEvent, useState } from "react";
import { errorText } from "../chat/useTranscript";

interface Props {
  onSignIn: (username: string, password: string) => Promise<void>;
}

export function LoginPage({ onSignIn }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: SyntheticEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSignIn(username, password);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  };

  return (
    <main className="login">
      <form onSubmit={(e) => void submit(e)} aria-label="Log in">
        <h1>Agent Chat</h1>
        <label>
          Username
          <input value={username} onChange={(e) => { setUsername(e.target.value); }} autoComplete="username" required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => { setPassword(e.target.value); }}
            autoComplete="current-password"
            required
          />
        </label>
        {error && <p role="alert" className="error">{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? "Logging in..." : "Log in"}
        </button>
      </form>
    </main>
  );
}
