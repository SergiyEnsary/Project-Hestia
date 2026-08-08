import { useEffect, useRef, useState } from "react";
import { isEchoAvailable, sendEcho } from "../api/client";

interface VoiceControlsProps {
  disabled: boolean;
  onExchange: (transcript: string, reply: string) => void;
  onError: (message: string | null) => void;
}

type VoiceState =
  | "idle"
  | "checking"
  | "listening"
  | "processing"
  | "ready"
  | "speaking";

function preferredMimeType(): string | undefined {
  const candidates = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type));
}

function decodeAudio(value: string): Uint8Array {
  const binary = atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

export function VoiceControls({ disabled, onExchange, onError }: VoiceControlsProps) {
  const [state, setState] = useState<VoiceState>("idle");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const recordingTimerRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  const releaseAudio = () => {
    audioRef.current?.pause();
    audioRef.current = null;
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    audioUrlRef.current = null;
  };

  const releaseStream = () => {
    if (recordingTimerRef.current !== null) {
      window.clearTimeout(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  };

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
      releaseStream();
      releaseAudio();
    };
  }, []);

  const playResponse = async (audioBase64: string) => {
    releaseAudio();
    const decoded = decodeAudio(audioBase64);
    const buffer = decoded.buffer.slice(
      decoded.byteOffset,
      decoded.byteOffset + decoded.byteLength
    ) as ArrayBuffer;
    const wav = new Blob([buffer], { type: "audio/wav" });
    const url = URL.createObjectURL(wav);
    const audio = new Audio(url);
    audioUrlRef.current = url;
    audioRef.current = audio;
    audio.onended = () => {
      releaseAudio();
      if (mountedRef.current) setState("idle");
    };
    setState("speaking");
    try {
      await audio.play();
    } catch {
      if (mountedRef.current) {
        setState("ready");
        onError("The browser blocked autoplay. Press Play reply.");
      }
    }
  };

  const resumePlayback = async () => {
    if (!audioRef.current) {
      setState("idle");
      return;
    }
    onError(null);
    try {
      await audioRef.current.play();
      setState("speaking");
    } catch {
      onError("The browser blocked Echo audio playback.");
    }
  };

  const processRecording = async (mimeType: string) => {
    releaseStream();
    const recording = new Blob(chunksRef.current, { type: mimeType || "audio/webm" });
    chunksRef.current = [];
    if (!recording.size) {
      setState("idle");
      onError("No audio was recorded.");
      return;
    }

    setState("processing");
    try {
      const response = await sendEcho(recording);
      if (!mountedRef.current) return;
      onExchange(response.transcript, response.message);
      await playResponse(response.audio_base64);
    } catch (error) {
      if (!mountedRef.current) return;
      setState("idle");
      onError(error instanceof Error ? error.message : "Echo is unavailable.");
    }
  };

  const startListening = async () => {
    if (disabled || state !== "idle") return;
    onError(null);
    setState("checking");
    if (!(await isEchoAvailable())) {
      setState("idle");
      onError("Echo is disabled or unavailable.");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setState("idle");
      onError("This browser does not support microphone recording.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const mimeType = preferredMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      streamRef.current = stream;
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        releaseStream();
        setState("idle");
        onError("Microphone recording failed.");
      };
      recorder.onstop = () => void processRecording(recorder.mimeType);
      recorder.start();
      recordingTimerRef.current = window.setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, 30_000);
      setState("listening");
    } catch {
      releaseStream();
      setState("idle");
      onError("Microphone permission was denied or unavailable.");
    }
  };

  const stop = () => {
    if (state === "listening" && recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    } else if (state === "speaking") {
      releaseAudio();
      setState("idle");
    }
  };

  const labels: Record<VoiceState, string> = {
    idle: "Talk to Hestia",
    checking: "Checking Echo…",
    listening: "Stop recording",
    processing: "Hestia is listening…",
    ready: "Play reply",
    speaking: "Stop speaking",
  };
  const active = state === "listening" || state === "speaking";

  return (
    <div className="voice-controls">
      <button
        type="button"
        className={`btn-voice${active ? " active" : ""}`}
        onClick={state === "ready" ? resumePlayback : active ? stop : startListening}
        disabled={disabled || state === "checking" || state === "processing"}
        aria-label={labels[state]}
        aria-pressed={active}
      >
        {state === "listening"
          ? "Stop"
          : state === "speaking"
            ? "Quiet"
            : state === "ready"
              ? "Play"
              : "Voice"}
      </button>
      <span className="voice-status" aria-live="polite">
        {state === "idle" ? "" : labels[state]}
      </span>
    </div>
  );
}
