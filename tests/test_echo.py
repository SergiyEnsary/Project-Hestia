from __future__ import annotations

import base64
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hestia.config import HestiaConfig
from hestia.interfaces.echo import EchoAudioTooLongError, EchoUnavailableError
from tests.conftest import TEST_TOKEN


@pytest.fixture
def echo_client(tmp_path: Path) -> Iterator[tuple[TestClient, MagicMock]]:
    config = HestiaConfig(
        api_token=TEST_TOKEN,
        modules={"zephyrus": {"enabled": False}},
        interfaces={
            "echo": {
                "enabled": True,
                "stt_model_path": tmp_path / "whisper",
                "tts_model_path": tmp_path / "voice.onnx",
            }
        },
    )

    with patch("hestia.api.app.EchoService") as service_class:
        service = service_class.return_value
        service.start = AsyncMock()
        service.close = AsyncMock()
        service.transcribe = AsyncMock(return_value="What is the weather?")
        service.synthesize = AsyncMock(return_value=b"RIFFtest-wave")

        from hestia.api.app import create_app

        with TestClient(create_app(config)) as test_client:
            test_client.app.state.orchestrator.run = AsyncMock(
                return_value=("fce3bd8a-7c16-4b21-b6ca-330072a03a17", "It is sunny.")
            )
            yield test_client, service


def test_echo_route_absent_when_disabled(client: TestClient, auth_headers: dict[str, str]):
    assert "/echo" not in client.app.openapi()["paths"]
    response = client.post("/echo", content=b"audio", headers=auth_headers)
    assert response.status_code in {404, 405}


def test_echo_conversation_success(
    echo_client: tuple[TestClient, MagicMock],
    auth_headers: dict[str, str],
):
    client, service = echo_client
    session_id = "6faf70ab-2c5f-44c9-a87d-cf7991da948c"
    response = client.post(
        "/echo",
        content=b"encoded audio",
        headers={
            **auth_headers,
            "Content-Type": "audio/webm; codecs=opus",
            "X-Hestia-Session-ID": session_id,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "fce3bd8a-7c16-4b21-b6ca-330072a03a17",
        "transcript": "What is the weather?",
        "message": "It is sunny.",
        "audio_base64": base64.b64encode(b"RIFFtest-wave").decode("ascii"),
        "audio_media_type": "audio/wav",
        "audio_truncated": False,
    }
    service.transcribe.assert_awaited_once_with(b"encoded audio", "audio/webm")
    client.app.state.orchestrator.run.assert_awaited_once_with(
        session_id,
        "What is the weather?",
    )
    service.synthesize.assert_awaited_once_with("It is sunny.")


def test_echo_status_and_microphone_policy(
    echo_client: tuple[TestClient, MagicMock],
    auth_headers: dict[str, str],
):
    client, _ = echo_client
    response = client.get("/echo", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert "microphone=(self)" in response.headers["permissions-policy"]


def test_echo_requires_auth(echo_client: tuple[TestClient, MagicMock]):
    client, service = echo_client
    response = client.post(
        "/echo",
        content=b"encoded audio",
        headers={"Content-Type": "audio/wav"},
    )
    assert response.status_code == 401
    service.transcribe.assert_not_awaited()


@pytest.mark.parametrize(
    ("headers", "body", "expected_status"),
    [
        ({"Content-Type": "application/octet-stream"}, b"audio", 415),
        ({"Content-Type": "audio/wav"}, b"", 422),
        (
            {
                "Content-Type": "audio/wav",
                "X-Hestia-Session-ID": "private-invalid-value",
            },
            b"audio",
            422,
        ),
    ],
)
def test_echo_rejects_invalid_requests(
    echo_client: tuple[TestClient, MagicMock],
    auth_headers: dict[str, str],
    headers: dict[str, str],
    body: bytes,
    expected_status: int,
):
    client, service = echo_client
    response = client.post(
        "/echo",
        content=body,
        headers={**auth_headers, **headers},
    )
    assert response.status_code == expected_status
    assert "private-invalid-value" not in response.text
    service.transcribe.assert_not_awaited()


def test_echo_rejects_oversize_stream(
    echo_client: tuple[TestClient, MagicMock],
    auth_headers: dict[str, str],
):
    client, service = echo_client
    client.app.state.config.interfaces.echo.max_audio_bytes = 1024
    response = client.post(
        "/echo",
        content=b"x" * 1025,
        headers={**auth_headers, "Content-Type": "audio/wav"},
    )
    assert response.status_code == 413
    service.transcribe.assert_not_awaited()


def test_echo_rejects_no_speech(
    echo_client: tuple[TestClient, MagicMock],
    auth_headers: dict[str, str],
):
    client, service = echo_client
    service.transcribe.return_value = "  "
    response = client.post(
        "/echo",
        content=b"audio",
        headers={**auth_headers, "Content-Type": "audio/wav"},
    )
    assert response.status_code == 422
    client.app.state.orchestrator.run.assert_not_awaited()


def test_echo_limits_spoken_reply(
    echo_client: tuple[TestClient, MagicMock],
    auth_headers: dict[str, str],
):
    client, service = echo_client
    client.app.state.config.interfaces.echo.max_tts_characters = 4
    client.app.state.orchestrator.run.return_value = ("session", "Long answer")
    response = client.post(
        "/echo",
        content=b"audio",
        headers={**auth_headers, "Content-Type": "audio/wav"},
    )
    assert response.status_code == 200
    assert response.json()["audio_truncated"] is True
    assert response.json()["message"] == "Long answer"
    service.synthesize.assert_awaited_once_with("Long")


@pytest.mark.parametrize(
    "failure",
    [
        EchoAudioTooLongError("private duration detail"),
        EchoUnavailableError("/private/model/path"),
    ],
)
def test_echo_sanitizes_speech_failures(
    echo_client: tuple[TestClient, MagicMock],
    auth_headers: dict[str, str],
    failure: Exception,
):
    client, service = echo_client
    service.transcribe.side_effect = failure
    response = client.post(
        "/echo",
        content=b"private audio",
        headers={**auth_headers, "Content-Type": "audio/wav"},
    )
    assert response.status_code in {422, 503}
    assert "private" not in response.text


def test_echo_uses_dedicated_rate_limit(
    echo_client: tuple[TestClient, MagicMock],
    auth_headers: dict[str, str],
):
    client, _ = echo_client
    client.app.state.config.interfaces.echo.rate_limit_per_minute = 1
    headers = {**auth_headers, "Content-Type": "audio/wav"}
    first = client.post("/echo", content=b"one", headers=headers)
    second = client.post("/echo", content=b"two", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 429
