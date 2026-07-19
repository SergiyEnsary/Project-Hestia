import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getSessionId,
  getToken,
  isEchoAvailable,
  sendEcho,
  setSessionId,
  setToken,
  streamChat,
  type StreamEvent,
} from "./client";

class MemoryStorage implements Storage {
  private values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

describe("Pythia API client", () => {
  beforeEach(() => {
    vi.stubGlobal("sessionStorage", new MemoryStorage());
    vi.stubGlobal("localStorage", new MemoryStorage());
    vi.stubGlobal("fetch", vi.fn());
  });

  it("stores credentials in their intended browser storage", () => {
    expect(getToken()).toBeNull();
    expect(getSessionId()).toBeNull();

    setToken("secret");
    setSessionId("session-1");

    expect(getToken()).toBe("secret");
    expect(getSessionId()).toBe("session-1");

    setToken("   ");
    expect(getToken()).toBeNull();
  });

  it("reports a missing token without making a request", async () => {
    const events: StreamEvent[] = [];

    await streamChat("hello", (event) => events.push(event));

    expect(events).toEqual([
      { type: "error", message: "API token not set. Open settings." },
    ]);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("reports unauthorized responses", async () => {
    setToken("bad-token");
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 401,
    } as Response);
    const events: StreamEvent[] = [];

    await streamChat("hello", (event) => events.push(event));

    expect(events).toEqual([
      { type: "error", message: "Unauthorized — check your API token." },
    ]);
  });

  it("reports a response without a stream", async () => {
    setToken("token");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      body: null,
    } as Response);
    const events: StreamEvent[] = [];

    await streamChat("hello", (event) => events.push(event));

    expect(events).toEqual([{ type: "error", message: "No response stream" }]);
  });

  it("checks Echo readiness without requesting microphone access", async () => {
    expect(await isEchoAvailable()).toBe(false);
    expect(fetch).not.toHaveBeenCalled();

    setToken("token");
    vi.mocked(fetch).mockResolvedValue({ ok: true } as Response);
    expect(await isEchoAvailable()).toBe(true);
    expect(fetch).toHaveBeenCalledWith("/echo", {
      headers: { Authorization: "Bearer token" },
    });
  });

  it("sends recorded audio to Echo and preserves its session", async () => {
    setToken("token");
    setSessionId("session-1");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        session_id: "session-2",
        transcript: "hello",
        message: "Hello there.",
        audio_base64: "UklGRg==",
        audio_media_type: "audio/wav",
        audio_truncated: false,
      }),
    } as unknown as Response);

    const response = await sendEcho(new Blob(["audio"], { type: "audio/webm" }));

    expect(response.transcript).toBe("hello");
    expect(getSessionId()).toBe("session-2");
    expect(fetch).toHaveBeenCalledWith(
      "/echo",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer token",
          "Content-Type": "audio/webm",
          "X-Hestia-Session-ID": "session-1",
        }),
      })
    );
  });

  it("rejects invalid Echo responses", async () => {
    setToken("token");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ session_id: "incomplete" }),
    } as unknown as Response);
    await expect(sendEcho(new Blob(["audio"]))).rejects.toThrow(
      "Echo returned an invalid response."
    );
  });

  it("reports network failures without exposing details", async () => {
    setToken("token");
    vi.mocked(fetch).mockRejectedValue(new Error("private network detail"));
    const events: StreamEvent[] = [];

    await streamChat("hello", (event) => events.push(event));

    expect(events).toEqual([
      { type: "error", message: "Unable to reach Hestia." },
    ]);
  });

  it("parses streamed events, ignores malformed data, and saves the session", async () => {
    setToken("token");
    const payload = [
      'data: {"type":"session","session_id":"session-2"}\r\n',
      "data: not-json\n",
      'data: {"type":"token","content":42}\n',
      'data: {"type":"unexpected"}\n',
      'data: {"type":"token","content":"Hello"}',
    ].join("");
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(payload),
        })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    };
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    } as unknown as Response);
    const events: StreamEvent[] = [];

    await streamChat("hello", (event) => events.push(event));

    expect(getSessionId()).toBe("session-2");
    expect(events).toEqual([
      { type: "session", session_id: "session-2" },
      { type: "token", content: "Hello" },
    ]);
    expect(fetch).toHaveBeenCalledWith(
      "/chat/stream",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ Accept: "text/event-stream" }),
      })
    );
  });
});
