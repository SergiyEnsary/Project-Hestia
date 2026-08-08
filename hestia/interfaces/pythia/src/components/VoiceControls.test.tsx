import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { isEchoAvailable, sendEcho } = vi.hoisted(() => ({
  isEchoAvailable: vi.fn(),
  sendEcho: vi.fn(),
}));

vi.mock("../api/client", () => ({ isEchoAvailable, sendEcho }));

import { VoiceControls } from "./VoiceControls";

class FakeMediaRecorder {
  static isTypeSupported = vi.fn(() => true);
  state = "inactive";
  mimeType: string;
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onerror: (() => void) | null = null;
  onstop: (() => void) | null = null;
  static emitEmptyChunk = false;

  constructor(_stream: MediaStream, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? "audio/webm";
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    const data = FakeMediaRecorder.emitEmptyChunk
      ? new Blob([], { type: this.mimeType })
      : new Blob(["audio"], { type: this.mimeType });
    this.ondataavailable?.({ data });
    this.onstop?.();
  }
}

describe("VoiceControls", () => {
  let playMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    isEchoAvailable.mockReset();
    sendEcho.mockReset();
    FakeMediaRecorder.emitEmptyChunk = false;
    FakeMediaRecorder.isTypeSupported = vi.fn(() => true);
    playMock = vi.fn().mockResolvedValue(undefined);

    vi.stubGlobal(
      "Audio",
      vi.fn(function Audio(this: { play: () => Promise<void>; pause: () => void; onended: (() => void) | null }) {
        this.play = playMock;
        this.pause = vi.fn();
        this.onended = null;
        return this;
      })
    );
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:audio"),
      revokeObjectURL: vi.fn(),
    });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reports when Echo is unavailable", async () => {
    const user = userEvent.setup();
    const onError = vi.fn();
    isEchoAvailable.mockResolvedValue(false);
    render(
      <VoiceControls disabled={false} onExchange={vi.fn()} onError={onError} />
    );

    await user.click(screen.getByRole("button", { name: "Talk to Hestia" }));
    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("Echo is disabled or unavailable.")
    );
  });

  it("records, posts audio, and plays the reply", async () => {
    const user = userEvent.setup();
    const onExchange = vi.fn();
    const onError = vi.fn();
    isEchoAvailable.mockResolvedValue(true);
    sendEcho.mockResolvedValue({
      session_id: "s1",
      transcript: "hello",
      message: "hi",
      audio_base64: btoa("wav"),
      audio_media_type: "audio/wav",
      audio_truncated: false,
    });

    render(
      <VoiceControls disabled={false} onExchange={onExchange} onError={onError} />
    );

    await user.click(screen.getByRole("button", { name: "Talk to Hestia" }));
    await screen.findByRole("button", { name: "Stop recording" });
    await user.click(screen.getByRole("button", { name: "Stop recording" }));

    await waitFor(() => expect(onExchange).toHaveBeenCalledWith("hello", "hi"));
    await waitFor(() => expect(playMock).toHaveBeenCalled());
  });

  it("surfaces Echo send failures", async () => {
    const user = userEvent.setup();
    const onError = vi.fn();
    isEchoAvailable.mockResolvedValue(true);
    sendEcho.mockRejectedValue(new Error("Echo is unavailable."));

    render(
      <VoiceControls disabled={false} onExchange={vi.fn()} onError={onError} />
    );

    await user.click(screen.getByRole("button", { name: "Talk to Hestia" }));
    await screen.findByRole("button", { name: "Stop recording" });
    await user.click(screen.getByRole("button", { name: "Stop recording" }));

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("Echo is unavailable.")
    );
  });

  it("reports missing browser recording support", async () => {
    const user = userEvent.setup();
    const onError = vi.fn();
    isEchoAvailable.mockResolvedValue(true);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: undefined,
    });

    render(
      <VoiceControls disabled={false} onExchange={vi.fn()} onError={onError} />
    );

    await user.click(screen.getByRole("button", { name: "Talk to Hestia" }));
    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(
        "This browser does not support microphone recording."
      )
    );
  });

  it("reports microphone permission failures", async () => {
    const user = userEvent.setup();
    const onError = vi.fn();
    isEchoAvailable.mockResolvedValue(true);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockRejectedValue(new Error("denied")),
      },
    });

    render(
      <VoiceControls disabled={false} onExchange={vi.fn()} onError={onError} />
    );

    await user.click(screen.getByRole("button", { name: "Talk to Hestia" }));
    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(
        "Microphone permission was denied or unavailable."
      )
    );
  });

  it("falls back when autoplay is blocked", async () => {
    const user = userEvent.setup();
    const onError = vi.fn();
    isEchoAvailable.mockResolvedValue(true);
    playMock.mockRejectedValue(new Error("autoplay"));
    sendEcho.mockResolvedValue({
      session_id: "s1",
      transcript: "hello",
      message: "hi",
      audio_base64: btoa("wav"),
      audio_media_type: "audio/wav",
      audio_truncated: false,
    });

    render(
      <VoiceControls disabled={false} onExchange={vi.fn()} onError={onError} />
    );

    await user.click(screen.getByRole("button", { name: "Talk to Hestia" }));
    await screen.findByRole("button", { name: "Stop recording" });
    await user.click(screen.getByRole("button", { name: "Stop recording" }));

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(
        "The browser blocked autoplay. Press Play reply."
      )
    );
    expect(await screen.findByRole("button", { name: "Play reply" })).toBeInTheDocument();
  });

  it("does nothing while disabled", async () => {
    const user = userEvent.setup();
    const onError = vi.fn();
    render(<VoiceControls disabled onExchange={vi.fn()} onError={onError} />);

    await user.click(screen.getByRole("button", { name: "Talk to Hestia" }));
    expect(isEchoAvailable).not.toHaveBeenCalled();
  });

  it("stops speaking when Quiet is pressed", async () => {
    const user = userEvent.setup();
    isEchoAvailable.mockResolvedValue(true);
    sendEcho.mockResolvedValue({
      session_id: "s1",
      transcript: "hello",
      message: "hi",
      audio_base64: btoa("wav"),
      audio_media_type: "audio/wav",
      audio_truncated: false,
    });

    render(
      <VoiceControls disabled={false} onExchange={vi.fn()} onError={vi.fn()} />
    );

    await user.click(screen.getByRole("button", { name: "Talk to Hestia" }));
    await screen.findByRole("button", { name: "Stop recording" });
    await user.click(screen.getByRole("button", { name: "Stop recording" }));
    await screen.findByRole("button", { name: "Stop speaking" });

    await user.click(screen.getByRole("button", { name: "Stop speaking" }));
    expect(screen.getByRole("button", { name: "Talk to Hestia" })).toBeInTheDocument();
  });

  it("reports empty recordings", async () => {
    const user = userEvent.setup();
    const onError = vi.fn();
    isEchoAvailable.mockResolvedValue(true);
    FakeMediaRecorder.emitEmptyChunk = true;

    render(
      <VoiceControls disabled={false} onExchange={vi.fn()} onError={onError} />
    );

    await user.click(screen.getByRole("button", { name: "Talk to Hestia" }));
    await screen.findByRole("button", { name: "Stop recording" });
    await user.click(screen.getByRole("button", { name: "Stop recording" }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("No audio was recorded."));
  });

  it("resumes blocked playback from the ready state", async () => {
    const user = userEvent.setup();
    const onError = vi.fn();
    isEchoAvailable.mockResolvedValue(true);
    playMock
      .mockRejectedValueOnce(new Error("autoplay"))
      .mockResolvedValueOnce(undefined);
    sendEcho.mockResolvedValue({
      session_id: "s1",
      transcript: "hello",
      message: "hi",
      audio_base64: btoa("wav"),
      audio_media_type: "audio/wav",
      audio_truncated: false,
    });

    render(
      <VoiceControls disabled={false} onExchange={vi.fn()} onError={onError} />
    );

    await user.click(screen.getByRole("button", { name: "Talk to Hestia" }));
    await screen.findByRole("button", { name: "Stop recording" });
    await user.click(screen.getByRole("button", { name: "Stop recording" }));
    await screen.findByRole("button", { name: "Play reply" });

    await user.click(screen.getByRole("button", { name: "Play reply" }));
    await waitFor(() => expect(playMock).toHaveBeenCalledTimes(2));
  });

  it("cleans up an active recorder on unmount", async () => {
    const user = userEvent.setup();
    isEchoAvailable.mockResolvedValue(true);
    const stopSpy = vi.spyOn(FakeMediaRecorder.prototype, "stop");

    const { unmount } = render(
      <VoiceControls disabled={false} onExchange={vi.fn()} onError={vi.fn()} />
    );

    await user.click(screen.getByRole("button", { name: "Talk to Hestia" }));
    await screen.findByRole("button", { name: "Stop recording" });

    act(() => {
      unmount();
    });
    expect(stopSpy).toHaveBeenCalled();
    stopSpy.mockRestore();
  });
});
