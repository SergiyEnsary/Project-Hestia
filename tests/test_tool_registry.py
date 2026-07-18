import json

import pytest

from hestia.core.tools.models import RiskLevel, ToolDefinition
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
                "properties": {"location": {"type": "string", "maxLength": 200}},
                "required": ["location"],
                "additionalProperties": False,
            },
        ),
        handler=handler,
    )


def test_register_and_list_tools(registry):
    class Mod:
        slug = "test"

        def get_tools(self):
            return [_make_tool()]

    registry.register_module(Mod())
    defs = registry.get_definitions()
    assert len(defs) == 1
    assert defs[0].name == "test.tool"
    assert "test.tool" in registry.get_tool_summary()


def test_duplicate_tool_raises(registry):
    class Mod:
        slug = "test"

        def get_tools(self):
            return [_make_tool(), _make_tool()]

    with pytest.raises(ValueError, match="Duplicate"):
        registry.register_module(Mod())


def test_registration_rejects_unbounded_schema(registry):
    tool = _make_tool()
    tool.definition.parameters["properties"]["location"].pop("maxLength")
    module = type(
        "M",
        (),
        {"slug": "test", "get_tools": lambda self: [tool]},
    )()
    with pytest.raises(ValueError, match="unbounded string"):
        registry.register_module(module)


@pytest.mark.asyncio
async def test_execute_success(registry):
    registry.register_module(
        type("M", (), {"slug": "test", "get_tools": lambda self: [_make_tool()]})()
    )
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
    registry.register_module(
        type("M", (), {"slug": "test", "get_tools": lambda self: [_make_tool()]})()
    )
    result = await registry.execute("test.tool", {})
    assert result.is_error is True
    assert result.error_code == "invalid_arguments"


@pytest.mark.asyncio
async def test_execute_rejects_wrong_argument_type(registry):
    registry.register_module(
        type("M", (), {"slug": "test", "get_tools": lambda self: [_make_tool()]})()
    )
    result = await registry.execute("test.tool", {"location": 123})
    assert result.is_error is True
    assert result.error_code == "invalid_arguments"


@pytest.mark.asyncio
async def test_execute_handler_exception(registry):
    async def bad_handler(args: dict) -> str:
        raise RuntimeError("boom")

    tool = RegisteredTool(
        definition=ToolDefinition(
            name="bad.tool",
            description="bad",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        handler=bad_handler,
    )
    registry.register_module(type("M", (), {"slug": "bad", "get_tools": lambda self: [tool]})())
    result = await registry.execute("bad.tool", {})
    assert result.is_error is True
    assert result.error_code == "tool_execution_failed"
    assert "boom" not in result.content
    assert result.correlation_id


@pytest.mark.asyncio
async def test_write_tools_fail_closed(registry):
    tool = _make_tool("test.write")
    tool.definition.risk_level = RiskLevel.WRITE
    registry.register_module(type("M", (), {"slug": "test", "get_tools": lambda self: [tool]})())
    result = await registry.execute("test.write", {"location": "Austin"})
    assert result.is_error is True
    assert result.error_code == "write_confirmation_required"


def test_format_result_json(registry):
    from hestia.core.tools.models import ToolResult

    formatted = registry.format_result(ToolResult(name="t", content='{"a":1}'))
    assert '"a"' in formatted


def test_format_result_error(registry):
    from hestia.core.tools.models import ToolResult

    formatted = registry.format_result(
        ToolResult(
            name="t",
            content="fail",
            is_error=True,
            error_code="tool_failed",
        )
    )
    assert formatted.startswith("Error from t (tool_failed):")
