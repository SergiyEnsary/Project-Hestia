from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from hestia.security.auth import verify_token

router = APIRouter(tags=["chat"])
_bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(...)
    session_id: str | None = None

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("message")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("message cannot be empty")
        return v

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError("session_id must be a valid UUID") from exc
        return v


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    message: str


async def _auth_dependency(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> None:
    await request.app.state.rate_limiter.check(request)
    await verify_token(request, credentials)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    body: ChatRequest,
    _: None = Depends(_auth_dependency),
) -> ChatResponse:
    config = request.app.state.config
    if len(body.message) > config.security.max_message_length:
        raise HTTPException(status_code=400, detail="Message too long")

    orchestrator = request.app.state.orchestrator
    session_id, reply = await orchestrator.run(body.session_id, body.message)
    return ChatResponse(session_id=session_id, message=reply)


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    _: None = Depends(_auth_dependency),
) -> StreamingResponse:
    import json

    config = request.app.state.config
    if len(body.message) > config.security.max_message_length:
        raise HTTPException(status_code=400, detail="Message too long")

    orchestrator = request.app.state.orchestrator

    async def event_generator() -> AsyncIterator[str]:
        try:
            session_id, full_text = await orchestrator.run(body.session_id, body.message)
        except Exception:
            correlation_id = request.state.correlation_id
            logger.exception(
                "Streaming chat failed (correlation_id=%s)",
                correlation_id,
            )
            payload = {
                "type": "error",
                "error": "internal_error",
                "correlation_id": correlation_id,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            return
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
        chunk_size = 24
        for i in range(0, len(full_text), chunk_size):
            chunk = full_text[i : i + chunk_size]
            yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    request: Request,
    _: None = Depends(_auth_dependency),
) -> Response:
    request.app.state.memory.clear(str(session_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
