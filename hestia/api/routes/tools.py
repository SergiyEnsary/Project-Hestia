from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from hestia.security.auth import verify_token

router = APIRouter(tags=["tools"])
_bearer = HTTPBearer(auto_error=False)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_id: str = Field(min_length=8, max_length=128)

    @field_validator("confirmation_id")
    @classmethod
    def validate_confirmation_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("confirmation_id cannot be empty")
        return cleaned


class ConfirmResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    is_error: bool
    error_code: str | None = None
    content: str
    correlation_id: str | None = None


async def _auth_dependency(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> None:
    await request.app.state.rate_limiter.check(request)
    await verify_token(request, credentials)


@router.post("/tools/confirm", response_model=ConfirmResponse)
async def confirm_tool(
    request: Request,
    body: ConfirmRequest,
    _: None = Depends(_auth_dependency),
) -> ConfirmResponse:
    registry = request.app.state.orchestrator._tools
    result = await registry.confirm_and_execute(body.confirmation_id)
    return ConfirmResponse(
        tool=result.name,
        is_error=result.is_error,
        error_code=result.error_code,
        content=result.content,
        correlation_id=result.correlation_id,
    )
