from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from hestia.security.auth import verify_token
from hestia.security.rate_limit import limiter

router = APIRouter(tags=["chat"])
_bearer = HTTPBearer(auto_error=False)


class ChatRequest(BaseModel):
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
    session_id: str
    message: str


async def _auth_dependency(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    await verify_token(request, credentials)


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
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
@limiter.limit("30/minute")
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

    async def event_generator():
        try:
            session_id, full_text = await orchestrator.run(body.session_id, body.message)
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
        chunk_size = 24
        for i in range(0, len(full_text), chunk_size):
            chunk = full_text[i : i + chunk_size]
            yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
