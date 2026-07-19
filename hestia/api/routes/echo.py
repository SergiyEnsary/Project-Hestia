from __future__ import annotations

import base64
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from hestia.interfaces.echo import EchoAudioTooLongError, EchoUnavailableError
from hestia.security.auth import verify_token

router = APIRouter(prefix="/echo", tags=["echo"])
_bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

_SUPPORTED_AUDIO_TYPES = {
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
}


class EchoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    transcript: str
    message: str
    audio_base64: str
    audio_media_type: str = "audio/wav"
    audio_truncated: bool


class EchoStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ready"


async def _auth_dependency(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> None:
    limit = request.app.state.config.interfaces.echo.rate_limit_per_minute
    await request.app.state.rate_limiter.check(request, limit=limit)
    await verify_token(request, credentials)


def _session_id_from_header(request: Request) -> str | None:
    value = request.headers.get("X-Hestia-Session-ID")
    if value is None:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid session identifier",
        ) from exc


async def _read_audio(request: Request, max_bytes: int) -> bytes:
    content_length = request.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Audio payload too large",
                )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length",
            ) from exc

    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Audio payload too large",
            )
        chunks.extend(chunk)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Audio payload is empty",
        )
    return bytes(chunks)


@router.get("", response_model=EchoStatusResponse)
async def echo_status(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> EchoStatusResponse:
    await verify_token(request, credentials)
    return EchoStatusResponse()


@router.post("", response_model=EchoResponse)
async def converse(
    request: Request,
    _: None = Depends(_auth_dependency),
) -> EchoResponse:
    media_type = request.headers.get("Content-Type", "").partition(";")[0].strip().lower()
    if media_type not in _SUPPORTED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported audio type",
        )

    config = request.app.state.config
    echo = request.app.state.echo
    audio = await _read_audio(request, config.interfaces.echo.max_audio_bytes)
    session_id = _session_id_from_header(request)

    try:
        transcript = (await echo.transcribe(audio, media_type)).strip()
        if not transcript:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="No speech detected",
            )
        if len(transcript) > config.security.max_message_length:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Transcript too long",
            )

        returned_session_id, reply = await request.app.state.orchestrator.run(
            session_id,
            transcript,
        )
        tts_limit = config.interfaces.echo.max_tts_characters
        spoken_reply = reply[:tts_limit]
        audio_reply = await echo.synthesize(spoken_reply)
    except EchoAudioTooLongError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Audio duration exceeds limit",
        ) from exc
    except EchoUnavailableError as exc:
        logger.warning(
            "Echo inference unavailable (correlation_id=%s)",
            request.state.correlation_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Echo is unavailable",
        ) from exc

    return EchoResponse(
        session_id=returned_session_id,
        transcript=transcript,
        message=reply,
        audio_base64=base64.b64encode(audio_reply).decode("ascii"),
        audio_truncated=len(reply) > tts_limit,
    )
