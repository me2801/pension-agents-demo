/** Shows the login page or the chat, and wires the real API client into the chat (dependency injection). */
import { useMemo } from "react";
import { HttpChatApi } from "./api/client";
import { LoginPage } from "./auth/LoginPage";
import { useAuth } from "./auth/useAuth";
import { ChatPage } from "./chat/ChatPage";

export function App() {
  const { token, signIn, signOut } = useAuth();
  const api = useMemo(() => (token ? new HttpChatApi(token, signOut) : null), [token, signOut]);
  if (!api) return <LoginPage onSignIn={signIn} />;
  return <ChatPage key={token} api={api} onSignOut={signOut} />;
}
