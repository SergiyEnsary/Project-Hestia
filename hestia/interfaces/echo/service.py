from __future__ import annotations

import asyncio
import importlib
import io
import wave
from typing import Any

from hestia.config import EchoConfig


class EchoUnavailableError(RuntimeError):
    """Raised when a local speech engine cannot be used."""


class EchoAudioTooLongError(ValueError):
    """Raised when decoded audio exceeds the configured duration limit."""


class EchoService:
    """Local speech-to-text and text-to-speech inference for Echo."""

    def __init__(self, config: EchoConfig) -> None:
        self._config = config
        self._stt_model: Any | None = None
        self._tts_voice: Any | None = None
        self._inference_slot = asyncio.Semaphore(1)

    async def start(self) -> None:
        await asyncio.to_thread(self._load_models)

    def _load_models(self) -> None:
        stt_path = self._config.stt_model_path
        tts_path = self._config.tts_model_path
        if stt_path is None or tts_path is None:
            raise EchoUnavailableError("Echo model paths are not configured")
        if not stt_path.exists() or not tts_path.exists():
            raise EchoUnavailableError("Echo model files are unavailable")

        try:
            whisper_module = importlib.import_module("faster_whisper")
            piper_module = importlib.import_module("piper")
        except ImportError as exc:
            raise EchoUnavailableError(
                'Echo dependencies are missing; install Hestia with the "echo" extra'
            ) from exc

        try:
            self._stt_model = whisper_module.WhisperModel(
                str(stt_path),
                device="cpu",
                compute_type=self._config.compute_type,
                local_files_only=True,
            )
            self._tts_voice = piper_module.PiperVoice.load(str(tts_path))
        except Exception as exc:
            raise EchoUnavailableError("Echo models could not be loaded") from exc

    async def transcribe(self, audio: bytes, media_type: str) -> str:
        del media_type  # The decoder detects the allowlisted encoded format.
        if self._stt_model is None:
            raise EchoUnavailableError("Echo speech recognition is unavailable")
        async with self._inference_slot:
            return await asyncio.to_thread(self._transcribe_sync, audio)

    def _transcribe_sync(self, audio: bytes) -> str:
        model = self._stt_model
        if model is None:
            raise EchoUnavailableError("Echo speech recognition is unavailable")
        try:
            segments, info = model.transcribe(
                io.BytesIO(audio),
                language=self._config.language,
                vad_filter=True,
                beam_size=5,
            )
            if info.duration > self._config.max_audio_seconds:
                raise EchoAudioTooLongError("Audio duration exceeds the configured limit")
            return " ".join(segment.text.strip() for segment in segments).strip()
        except EchoAudioTooLongError:
            raise
        except Exception as exc:
            raise EchoUnavailableError("Audio could not be transcribed") from exc

    async def synthesize(self, text: str) -> bytes:
        if self._tts_voice is None:
            raise EchoUnavailableError("Echo speech synthesis is unavailable")
        async with self._inference_slot:
            return await asyncio.to_thread(self._synthesize_sync, text)

    def _synthesize_sync(self, text: str) -> bytes:
        voice = self._tts_voice
        if voice is None:
            raise EchoUnavailableError("Echo speech synthesis is unavailable")
        output = io.BytesIO()
        try:
            with wave.open(output, "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)
        except Exception as exc:
            raise EchoUnavailableError("Speech could not be synthesized") from exc
        audio = output.getvalue()
        if len(audio) > self._config.max_tts_audio_bytes:
            raise EchoUnavailableError("Synthesized speech exceeds the configured limit")
        return audio

    async def close(self) -> None:
        self._stt_model = None
        self._tts_voice = None
