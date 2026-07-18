import json

import pytest

from hestia.core.tools.models import ToolDefinition
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.base import RegisteredTool


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


def _make_tool(name: str = "test.tool") -> RegisteredTool:
    async def handler(args: dict) -> str:
        return json.dumps({"ok": True, "args": args})

    return RegisteredTool(
        definition=ToolDefinition(
            name=name,
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        ),
        handler=handler,
    )


def test_register_and_list_tools(registry):
    class Mod:
        def get_tools(self):
            return [_make_tool()]

    registry.register_module(Mod())
    defs = registry.get_definitions()
    assert len(defs) == 1
    assert defs[0].name == "test.tool"
    assert "test.tool" in registry.get_tool_summary()


def test_duplicate_tool_raises(registry):
    class Mod:
        def get_tools(self):
            return [_make_tool(), _make_tool()]

    with pytest.raises(ValueError, match="Duplicate"):
        registry.register_module(Mod())


@pytest.mark.asyncio
async def test_execute_success(registry):
    registry.register_module(type("M", (), {"get_tools": lambda self: [_make_tool()]})())
    result = await registry.execute("test.tool", {"location": "Austin"})
    assert result.is_error is False
    data = json.loads(result.content)
    assert data["args"]["location"] == "Austin"


@pytest.mark.asyncio
async def test_execute_unknown_tool(registry):
    result = await registry.execute("missing.tool", {})
    assert result.is_error is True


@pytest.mark.asyncio
async def test_execute_missing_required_arg(registry):
    registry.register_module(type("M", (), {"get_tools": lambda self: [_make_tool()]})())
    result = await registry.execute("test.tool", {})
    assert result.is_error is True
    assert "Missing required" in result.content


@pytest.mark.asyncio
async def test_execute_handler_exception(registry):
    async def bad_handler(args: dict) -> str:
        raise RuntimeError("boom")

    tool = RegisteredTool(
        definition=ToolDefinition(
            name="bad.tool",
            description="bad",
            parameters={"type": "object", "properties": {}},
        ),
        handler=bad_handler,
    )
    registry.register_module(type("M", (), {"get_tools": lambda self: [tool]})())
    result = await registry.execute("bad.tool", {})
    assert result.is_error is True
    assert "boom" in result.content


def test_format_result_json(registry):
    from hestia.core.tools.models import ToolResult

    formatted = registry.format_result(ToolResult(name="t", content='{"a":1}'))
    assert '"a"' in formatted


def test_format_result_error(registry):
    from hestia.core.tools.models import ToolResult

    formatted = registry.format_result(ToolResult(name="t", content="fail", is_error=True))
    assert formatted.startswith("Error from t:")
