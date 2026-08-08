import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MessageInput } from "./MessageInput";

describe("MessageInput", () => {
  it("sends trimmed text on submit and clears the field", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageInput onSend={onSend} disabled={false} />);

    const input = screen.getByPlaceholderText("Ask Hestia anything…");
    await user.type(input, "  hello  ");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(onSend).toHaveBeenCalledWith("  hello  ");
    expect(input).toHaveValue("");
  });

  it("does not send blank messages", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageInput onSend={onSend} disabled={false} />);

    await user.type(screen.getByPlaceholderText("Ask Hestia anything…"), "   ");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(onSend).not.toHaveBeenCalled();
  });

  it("submits on Enter without Shift", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageInput onSend={onSend} disabled={false} />);

    const input = screen.getByPlaceholderText("Ask Hestia anything…");
    await user.type(input, "ping{Enter}");

    expect(onSend).toHaveBeenCalledWith("ping");
  });
});
