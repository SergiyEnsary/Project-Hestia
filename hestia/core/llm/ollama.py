from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

from hestia.config import LLMConfig
from hestia.core.llm.errors import OllamaUnavailableError
from hestia.core.tools.models import ChatMessage, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)


class OllamaProvider:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout_seconds,
        )

    def _to_ollama_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                result.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": tc.name,
                                    "arguments": tc.arguments,
                                }
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
            elif msg.role == "tool":
                result.append(
                    {
                        "role": "tool",
                        "content": msg.content or "",
                    }
                )
            else:
                entry: dict[str, Any] = {"role": msg.role, "content": msg.content or ""}
                result.append(entry)
        return result

    def _to_ollama_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _parse_response(self, data: dict[str, Any]) -> ChatMessage:
        message = data.get("message", {})
        content = message.get("content") or ""
        tool_calls: list[ToolCall] = []

        for tc in message.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(ToolCall(name=fn.get("name", ""), arguments=args))

        return ChatMessage(role="assistant", content=content, tool_calls=tool_calls)

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> ChatMessage:
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": self._to_ollama_messages(messages),
            "stream": False,
        }
        if tools:
            payload["tools"] = self._to_ollama_tools(tools)

        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise OllamaUnavailableError(self._config.base_url) from exc
        return self._parse_response(response.json())

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[str]:
        # Run full chat for tool loop; stream only final text response
        result = await self.chat(messages, tools)
        if result.content:
            yield result.content

    async def close(self) -> None:
        await self._client.aclose()
