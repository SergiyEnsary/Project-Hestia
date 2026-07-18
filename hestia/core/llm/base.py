from __future__ import annotations

from hestia.core.tools.models import ChatMessage, ToolCall, ToolDefinition

from typing import AsyncIterator, Protocol


class LLMProvider(Protocol):
    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> ChatMessage: ...

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[str]: ...

    async def close(self) -> None: ...
