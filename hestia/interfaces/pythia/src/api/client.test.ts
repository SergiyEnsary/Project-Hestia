import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getSessionId,
  getToken,
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

  it("parses streamed events, ignores malformed data, and saves the session", async () => {
    setToken("token");
    const payload = [
      'data: {"type":"session","session_id":"session-2"}\n',
      "data: not-json\n",
      'data: {"type":"token","content":"Hello"}\n',
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
  });
});
