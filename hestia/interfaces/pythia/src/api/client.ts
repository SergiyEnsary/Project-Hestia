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

export interface EchoResponse {
  session_id: string;
  transcript: string;
  message: string;
  audio_base64: string;
  audio_media_type: "audio/wav";
  audio_truncated: boolean;
}

function authorizationHeaders(): Record<string, string> | null {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : null;
}

export async function isEchoAvailable(): Promise<boolean> {
  const headers = authorizationHeaders();
  if (!headers) return false;
  try {
    const response = await fetch("/echo", { headers });
    return response.ok;
  } catch {
    return false;
  }
}

function parseEchoResponse(value: unknown): EchoResponse | null {
  if (typeof value !== "object" || value === null) return null;
  const response = value as Record<string, unknown>;
  if (
    typeof response.session_id !== "string" ||
    typeof response.transcript !== "string" ||
    typeof response.message !== "string" ||
    typeof response.audio_base64 !== "string" ||
    response.audio_media_type !== "audio/wav" ||
    typeof response.audio_truncated !== "boolean"
  ) {
    return null;
  }
  return response as unknown as EchoResponse;
}

export async function sendEcho(audio: Blob): Promise<EchoResponse> {
  const headers = authorizationHeaders();
  if (!headers) throw new Error("Set your API token in settings first.");
  const sessionId = getSessionId();
  const response = await fetch("/echo", {
    method: "POST",
    headers: {
      ...headers,
      "Content-Type": audio.type || "audio/webm",
      ...(sessionId ? { "X-Hestia-Session-ID": sessionId } : {}),
    },
    body: audio,
  });
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("Unauthorized — check your API token.");
    }
    if (response.status === 413) {
      throw new Error("Recording is too large.");
    }
    if (response.status === 422) {
      throw new Error("No usable speech was detected.");
    }
    throw new Error("Echo is unavailable.");
  }
  const parsed = parseEchoResponse(await response.json());
  if (!parsed) throw new Error("Echo returned an invalid response.");
  setSessionId(parsed.session_id);
  return parsed;
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
