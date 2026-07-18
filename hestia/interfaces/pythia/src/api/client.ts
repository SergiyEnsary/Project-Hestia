const TOKEN_KEY = "hestia_api_token";
const SESSION_KEY = "hestia_session_id";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  const normalized = token.trim();
  if (normalized) {
    sessionStorage.setItem(TOKEN_KEY, normalized);
  } else {
    sessionStorage.removeItem(TOKEN_KEY);
  }
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
  error?: string;
  correlation_id?: string;
}

function parseStreamEvent(value: unknown): StreamEvent | null {
  if (typeof value !== "object" || value === null) return null;
  const event = value as Record<string, unknown>;
  switch (event.type) {
    case "session":
      return typeof event.session_id === "string"
        ? { type: "session", session_id: event.session_id }
        : null;
    case "token":
      return typeof event.content === "string"
        ? { type: "token", content: event.content }
        : null;
    case "done":
      return { type: "done" };
    case "error":
      if (event.message !== undefined && typeof event.message !== "string") {
        return null;
      }
      if (event.error !== undefined && typeof event.error !== "string") {
        return null;
      }
      if (
        event.correlation_id !== undefined &&
        typeof event.correlation_id !== "string"
      ) {
        return null;
      }
      return {
        type: "error",
        message: event.message,
        error: event.error,
        correlation_id: event.correlation_id,
      };
    default:
      return null;
  }
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
  let response: Response;
  try {
    response = await fetch("/chat/stream", {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        message,
        session_id: sessionId,
      }),
    });
  } catch {
    onEvent({ type: "error", message: "Unable to reach Hestia." });
    return;
  }

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

  const processLine = (line: string): void => {
    if (!line.startsWith("data: ")) return;
    try {
      const event = parseStreamEvent(JSON.parse(line.slice(6)));
      if (!event) return;
      if (event.type === "session" && event.session_id) {
        setSessionId(event.session_id);
      }
      onEvent(event);
    } catch {
      // Ignore malformed SSE lines without exposing parser details.
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        if (buffer) processLine(buffer.replace(/\r$/, ""));
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? "";
      for (const line of lines) processLine(line);
    }
  } catch {
    onEvent({ type: "error", message: "The response stream was interrupted." });
  }
}
