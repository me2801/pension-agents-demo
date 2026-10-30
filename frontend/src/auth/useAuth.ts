/** The access token, kept in sessionStorage: it survives a reload but not closing the tab. */
import { useCallback, useState } from "react";
import { login } from "../api/client";

const STORAGE_KEY = "agent-chat-token";

function readToken(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // storage can be blocked (e.g. private mode); then the user just logs in again
  }
}

function writeToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(STORAGE_KEY, token);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // see readToken
  }
}

export interface Auth {
  token: string | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => void;
}

export function useAuth(): Auth {
  const [token, setToken] = useState<string | null>(readToken);

  const signIn = useCallback(async (username: string, password: string) => {
    const issued = await login(username, password);
    writeToken(issued.access_token);
    setToken(issued.access_token);
  }, []);

  const signOut = useCallback(() => {
    writeToken(null);
    setToken(null);
  }, []);

  return { token, signIn, signOut };
}
