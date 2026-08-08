import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getToken, streamChat } = vi.hoisted(() => ({
  getToken: vi.fn(() => null as string | null),
  streamChat: vi.fn(),
}));

vi.mock("../api/client", () => ({ getToken, streamChat }));

import { useChat } from "./useChat";

describe("useChat", () => {
  beforeEach(() => {
    getToken.mockReturnValue("token");
    streamChat.mockReset();
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "id-" + Math.random()) });
  });

  it("requires a token before sending", async () => {
    getToken.mockReturnValue(null);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage("hello");
    });

    expect(result.current.error).toBe("Set your API token in settings first.");
    expect(streamChat).not.toHaveBeenCalled();
  });

  it("streams tokens into an assistant message", async () => {
    streamChat.mockImplementation(async (_text, onEvent) => {
      onEvent({ type: "token", content: "Hel" });
      onEvent({ type: "token", content: "lo" });
      onEvent({ type: "done" });
    });
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage("hi");
    });

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0]?.content).toBe("hi");
    expect(result.current.messages[1]?.content).toBe("Hello");
    expect(result.current.loading).toBe(false);
  });

  it("surfaces stream errors", async () => {
    streamChat.mockImplementation(async (_text, onEvent) => {
      onEvent({ type: "error", message: "boom" });
    });
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage("hi");
    });

    expect(result.current.error).toBe("boom");
    expect(result.current.loading).toBe(false);
  });

  it("adds voice exchanges", () => {
    const { result } = renderHook(() => useChat());

    act(() => {
      result.current.addExchange("said", "heard");
    });

    expect(result.current.messages.map((message) => message.content)).toEqual([
      "said",
      "heard",
    ]);
  });

  it("ignores blank sends while idle", async () => {
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage("   ");
    });

    expect(streamChat).not.toHaveBeenCalled();
  });
});
