from __future__ import annotations

from enum import Enum
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    READ = "read"
    WRITE = "write"


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    risk_level: RiskLevel = RiskLevel.READ


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    name: str
    content: str
    is_error: bool = False


class ChatMessage(BaseModel):
    role: str
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


ToolHandler = Callable[[dict[str, Any]], Awaitable[str]]
