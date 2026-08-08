import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getToken, useChat } = vi.hoisted(() => ({
  getToken: vi.fn(() => "token" as string | null),
  useChat: vi.fn(),
}));

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<typeof import("./api/client")>("./api/client");
  return { ...actual, getToken };
});

vi.mock("./hooks/useChat", () => ({ useChat }));

vi.mock("./components/VoiceControls", () => ({
  VoiceControls: () => <div data-testid="voice-controls" />,
}));

import App from "./App";

describe("App", () => {
  beforeEach(() => {
    getToken.mockReturnValue("token");
    useChat.mockReturnValue({
      messages: [],
      loading: false,
      error: null,
      sendMessage: vi.fn(),
      addExchange: vi.fn(),
      setError: vi.fn(),
    });
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("opens settings when no token is stored", () => {
    getToken.mockReturnValue(null);
    render(<App />);
    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByLabelText("API Token")).toBeInTheDocument();
  });

  it("shows stream errors and opens settings on demand", async () => {
    const user = userEvent.setup();
    useChat.mockReturnValue({
      messages: [],
      loading: false,
      error: "Something failed",
      sendMessage: vi.fn(),
      addExchange: vi.fn(),
      setError: vi.fn(),
    });
    render(<App />);

    expect(screen.getByText("Something failed")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByLabelText("API Token")).toBeInTheDocument();
  });
});
