from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from hestia.config import EchoConfig
from hestia.interfaces.echo import (
    EchoAudioTooLongError,
    EchoService,
    EchoUnavailableError,
)


def test_echo_service_requires_existing_models(tmp_path: Path):
    service = EchoService(
        EchoConfig(
            enabled=True,
            stt_model_path=tmp_path / "missing-whisper",
            tts_model_path=tmp_path / "missing-voice.onnx",
        )
    )
    with pytest.raises(EchoUnavailableError):
        service._load_models()


async def test_echo_service_transcribes_and_enforces_duration():
    service = EchoService(EchoConfig(max_audio_seconds=10))
    model = MagicMock()
    model.transcribe.return_value = (
        iter([SimpleNamespace(text=" hello "), SimpleNamespace(text="world")]),
        SimpleNamespace(duration=2.5),
    )
    service._stt_model = model

    assert await service.transcribe(b"audio", "audio/wav") == "hello world"

    model.transcribe.return_value = (iter([]), SimpleNamespace(duration=11))
    with pytest.raises(EchoAudioTooLongError):
        await service.transcribe(b"audio", "audio/wav")


async def test_echo_service_synthesizes_bounded_wav():
    service = EchoService(EchoConfig(max_tts_audio_bytes=1024))
    voice = MagicMock()

    def synthesize(_text, wav_file):
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\0" * 100)

    voice.synthesize_wav.side_effect = synthesize
    service._tts_voice = voice
    audio = await service.synthesize("hello")
    assert audio.startswith(b"RIFF")
    assert len(audio) < 1024

    def synthesize_too_much(_text, wav_file):
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\0" * 1100)

    voice.synthesize_wav.side_effect = synthesize_too_much
    with pytest.raises(EchoUnavailableError):
        await service.synthesize("hello")


async def test_echo_service_close_releases_models():
    service = EchoService(EchoConfig())
    service._stt_model = MagicMock()
    service._tts_voice = MagicMock()
    await service.close()
    assert service._stt_model is None
    assert service._tts_voice is None
