import json
from unittest.mock import AsyncMock

import pytest

from hestia.config import HestiaConfig
from hestia.core.llm.errors import OllamaUnavailableError
from hestia.core.mnemosyne import Mnemosyne
from hestia.core.orchestrator import Orchestrator
from hestia.core.tools.models import ChatMessage, ToolCall
from hestia.core.tools.registry import ToolRegistry


@pytest.fixture
def config() -> HestiaConfig:
    return HestiaConfig(api_token="test")


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    return llm


@pytest.mark.asyncio
async def test_orchestrator_simple_reply(config, registry, mock_llm):
    mock_llm.chat = AsyncMock(
        return_value=ChatMessage(role="assistant", content="Hello from Hestia!")
    )
    memory = Mnemosyne()
    orchestrator = Orchestrator(config, mock_llm, registry, memory)

    session_id, reply = await orchestrator.run(None, "Hi")
    assert reply == "Hello from Hestia!"
    assert session_id
    assert len(memory.get_messages(session_id)) == 2


@pytest.mark.asyncio
async def test_orchestrator_tool_loop(config, mock_llm):
    registry = ToolRegistry()

    async def weather_handler(args: dict) -> str:
        return json.dumps({"temperature": "22°C"})

    from hestia.core.tools.models import ToolDefinition

    tool_def = ToolDefinition(
        name="zephyrus.get_current_weather",
        description="Get weather",
        parameters={
            "type": "object",
            "properties": {"location": {"type": "string", "maxLength": 200}},
            "additionalProperties": False,
        },
    )

    class FakeModule:
        slug = "zephyrus"

        def get_tools(self):
            from hestia.modules.base import RegisteredTool

            return [RegisteredTool(definition=tool_def, handler=weather_handler)]

    registry.register_module(FakeModule())

    mock_llm.chat = AsyncMock(
        side_effect=[
            ChatMessage(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(name="zephyrus.get_current_weather", arguments={"location": "London"})
                ],
            ),
            ChatMessage(role="assistant", content="It is 22°C in London."),
        ]
    )

    memory = Mnemosyne()
    orchestrator = Orchestrator(config, mock_llm, registry, memory)
    session_id, reply = await orchestrator.run(None, "What's the weather in London?")

    assert "22" in reply
    assert mock_llm.chat.call_count == 2


@pytest.mark.asyncio
async def test_orchestrator_ollama_unavailable(config, registry, mock_llm):
    mock_llm.chat = AsyncMock(side_effect=OllamaUnavailableError("http://127.0.0.1:11434"))
    memory = Mnemosyne()
    orchestrator = Orchestrator(config, mock_llm, registry, memory)

    session_id, reply = await orchestrator.run(None, "Hi")
    assert "Cannot connect to Ollama" in reply
    assert len(memory.get_messages(session_id)) == 2


@pytest.mark.asyncio
async def test_orchestrator_max_tool_iterations(config, mock_llm):
    registry = ToolRegistry()

    async def handler(args: dict) -> str:
        return '{"done": true}'

    from hestia.core.tools.models import ToolDefinition
    from hestia.modules.base import RegisteredTool

    tool = RegisteredTool(
        definition=ToolDefinition(
            name="loop.tool",
            description="loops",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        handler=handler,
    )
    registry.register_module(type("M", (), {"slug": "loop", "get_tools": lambda self: [tool]})())

    mock_llm.chat = AsyncMock(
        return_value=ChatMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCall(name="loop.tool", arguments={})],
        )
    )

    config.security.max_tool_iterations = 2
    memory = Mnemosyne()
    orchestrator = Orchestrator(config, mock_llm, registry, memory)
    _, reply = await orchestrator.run(None, "loop forever")

    assert "maximum number of tool calls" in reply
    assert mock_llm.chat.call_count == 2
