import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatWindow } from "./ChatWindow";

describe("ChatWindow", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("shows the empty state when there are no messages", () => {
    render(<ChatWindow messages={[]} loading={false} />);
    expect(screen.getByText("Consult Hestia")).toBeInTheDocument();
  });

  it("renders user and assistant messages", () => {
    render(
      <ChatWindow
        messages={[
          { id: "1", role: "user", content: "Hi" },
          { id: "2", role: "assistant", content: "Hello" },
        ]}
        loading={false}
      />
    );
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("Hi")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("shows a typing indicator while loading", () => {
    render(<ChatWindow messages={[]} loading />);
    expect(screen.getByText("Thinking…")).toBeInTheDocument();
  });
});
