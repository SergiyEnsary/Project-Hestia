import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getToken, setToken } = vi.hoisted(() => ({
  getToken: vi.fn(() => null as string | null),
  setToken: vi.fn(),
}));

vi.mock("../api/client", () => ({ getToken, setToken }));

import { SettingsModal } from "./SettingsModal";

describe("SettingsModal", () => {
  beforeEach(() => {
    getToken.mockReturnValue(null);
    setToken.mockReset();
  });

  it("renders nothing when closed", () => {
    const { container } = render(<SettingsModal open={false} onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("saves a trimmed token and closes", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<SettingsModal open onClose={onClose} />);

    await user.type(screen.getByLabelText("API Token"), "  secret  ");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(setToken).toHaveBeenCalledWith("secret");
    expect(onClose).toHaveBeenCalled();
  });

  it("closes from cancel and overlay clicks", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { container } = render(<SettingsModal open onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledTimes(1);

    await user.click(container.querySelector(".modal-overlay")!);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
