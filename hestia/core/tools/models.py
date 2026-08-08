from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskLevel(StrEnum):
    READ = "read"
    WRITE = "write"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolDefinition(StrictModel):
    name: str
    description: str = Field(min_length=1, max_length=500)
    parameters: dict[str, Any]
    risk_level: RiskLevel = RiskLevel.READ

    @field_validator("name")
    @classmethod
    def validate_namespaced_name(cls, value: str) -> str:
        if re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", value) is None:
            raise ValueError("tool names must use the '<module>.<tool>' namespace")
        return value


class ToolCall(StrictModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(StrictModel):
    name: str
    content: str
    is_error: bool = False
    error_code: str | None = None
    correlation_id: str | None = None


class ChatMessage(StrictModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


ToolHandler = Callable[[dict[str, Any]], Awaitable[str]]
