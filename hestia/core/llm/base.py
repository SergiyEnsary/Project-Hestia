from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from hestia.core.tools.models import ChatMessage, ToolDefinition


class LLMProvider(Protocol):
    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> ChatMessage: ...

    def chat_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[str]: ...

    async def close(self) -> None: ...
