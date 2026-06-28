const TOKEN_KEY = "hestia_api_token";
const SESSION_KEY = "hestia_session_id";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function getSessionId(): string | null {
  return localStorage.getItem(SESSION_KEY);
}

export function setSessionId(id: string): void {
  localStorage.setItem(SESSION_KEY, id);
}

export interface StreamEvent {
  type: "session" | "token" | "done" | "error";
  session_id?: string;
  content?: string;
  message?: string;
}

export async function streamChat(
  message: string,
  onEvent: (event: StreamEvent) => void
): Promise<void> {
  const token = getToken();
  if (!token) {
    onEvent({ type: "error", message: "API token not set. Open settings." });
    return;
  }

  const sessionId = getSessionId();
  const response = await fetch("/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
    }),
  });

  if (!response.ok) {
    onEvent({
      type: "error",
      message: response.status === 401 ? "Unauthorized — check your API token." : `Error ${response.status}`,
    });
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onEvent({ type: "error", message: "No response stream" });
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const event = JSON.parse(line.slice(6)) as StreamEvent;
          if (event.type === "session" && event.session_id) {
            setSessionId(event.session_id);
          }
          onEvent(event);
        } catch {
          // ignore malformed SSE lines
        }
      }
    }
  }
}
