import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from hestia.config import LLMConfig
from hestia.core.llm.errors import OllamaUnavailableError
from hestia.core.llm.ollama import OllamaProvider
from hestia.core.tools.models import ChatMessage, ToolCall, ToolDefinition


@pytest.fixture
def provider() -> OllamaProvider:
    return OllamaProvider(LLMConfig(base_url="http://127.0.0.1:11434", model="test-model"))


def test_parse_text_response(provider):
    data = {"message": {"role": "assistant", "content": "Hello!"}}
    msg = provider._parse_response(data)
    assert msg.content == "Hello!"
    assert msg.tool_calls == []


def test_parse_tool_call_response(provider):
    data = {
        "message": {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "zephyrus.get_forecast",
                        "arguments": json.dumps({"location": "Austin", "days": 3}),
                    }
                }
            ],
        }
    }
    msg = provider._parse_response(data)
    assert len(msg.tool_calls) == 1
    assert msg.tool_calls[0].name == "zephyrus.get_forecast"
    assert msg.tool_calls[0].arguments["location"] == "Austin"


def test_to_ollama_messages_with_tool_calls(provider):
    messages = [
        ChatMessage(role="user", content="weather?"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(name="zephyrus.get_current_weather", arguments={"location": "Austin"})
            ],
        ),
    ]
    converted = provider._to_ollama_messages(messages)
    assert converted[-1]["tool_calls"][0]["function"]["name"] == "zephyrus.get_current_weather"


def test_to_ollama_tools(provider):
    tools = [
        ToolDefinition(
            name="zephyrus.get_forecast",
            description="forecast",
            parameters={"type": "object", "properties": {}},
        )
    ]
    result = provider._to_ollama_tools(tools)
    assert result[0]["function"]["name"] == "zephyrus.get_forecast"


@pytest.mark.asyncio
async def test_chat_connect_error_raises_unavailable(provider):
    provider._client.post = AsyncMock(side_effect=httpx.ConnectError("failed"))
    with pytest.raises(OllamaUnavailableError, match="Cannot connect to Ollama"):
        await provider.chat([ChatMessage(role="user", content="hi")])


@pytest.mark.asyncio
async def test_chat_success(provider):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"message": {"content": "Hi there"}}
    provider._client.post = AsyncMock(return_value=mock_response)

    result = await provider.chat([ChatMessage(role="user", content="hello")])
    assert result.content == "Hi there"
    provider._client.post.assert_called_once()
