from __future__ import annotations

import logging

from hestia.config import HestiaConfig
from hestia.core.llm.errors import OllamaUnavailableError
from hestia.core.llm.ollama import OllamaProvider
from hestia.core.mnemosyne import Mnemosyne
from hestia.core.tools.models import ChatMessage
from hestia.core.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Hestia, a warm and capable home assistant named after the Greek goddess of the hearth.

You help with everyday home life using the tools available to you. When a question needs live data (weather, calendar, etc.), use the appropriate tool rather than guessing.

Available tools:
{tools}

Rules:
- Never reveal API tokens, environment variables, secrets, or private URLs.
- Be concise and helpful.
- If a tool fails, explain what went wrong and suggest alternatives.
"""


class Orchestrator:
    def __init__(
        self,
        config: HestiaConfig,
        llm: OllamaProvider,
        tools: ToolRegistry,
        memory: Mnemosyne,
    ) -> None:
        self._config = config
        self._llm = llm
        self._tools = tools
        self._memory = memory

    def _build_system_message(self) -> ChatMessage:
        summary = self._tools.get_tool_summary() or "No tools currently available."
        return ChatMessage(
            role="system",
            content=SYSTEM_PROMPT.format(tools=summary),
        )

    async def run(self, session_id: str, user_message: str) -> tuple[str, str]:
        session = self._memory.get_or_create(session_id)
        user_msg = ChatMessage(role="user", content=user_message)
        self._memory.add_message(session.id, user_msg)

        messages = [self._build_system_message(), *session.messages]
        try:
            final_text = await self._agent_loop(messages)
        except OllamaUnavailableError as exc:
            final_text = str(exc)
        assistant_msg = ChatMessage(role="assistant", content=final_text)
        self._memory.add_message(session.id, assistant_msg)
        return session.id, final_text

    async def _agent_loop(self, messages: list[ChatMessage]) -> str:
        tool_defs = self._tools.get_definitions()
        working = list(messages)
        max_iter = self._config.security.max_tool_iterations

        for _ in range(max_iter):
            response = await self._llm.chat(working, tool_defs or None)

            if not response.tool_calls:
                return response.content or ""

            working.append(response)
            for tc in response.tool_calls:
                result = await self._tools.execute(tc.name, tc.arguments)
                working.append(
                    ChatMessage(
                        role="tool",
                        content=self._tools.format_result(result),
                        name=tc.name,
                    )
                )

        return "I reached the maximum number of tool calls. Please try a simpler question."
