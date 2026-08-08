from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from hestia.core.tools.confirmation import WriteConfirmationStore, argument_fingerprint
from hestia.core.tools.models import RiskLevel, ToolDefinition
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.base import RegisteredTool


@pytest.mark.asyncio
async def test_write_confirmation_create_and_one_use_execute():
    async def handler(args: dict) -> str:
        return json.dumps({"written": args["value"]})

    tool = RegisteredTool(
        definition=ToolDefinition(
            name="test.write",
            description="write",
            risk_level=RiskLevel.WRITE,
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string", "maxLength": 20}},
                "required": ["value"],
                "additionalProperties": False,
            },
        ),
        handler=handler,
    )
    registry = ToolRegistry()
    registry.register_module(type("M", (), {"slug": "test", "get_tools": lambda self: [tool]})())

    blocked = await registry.execute("test.write", {"value": "lamp"})
    assert blocked.is_error is True
    assert blocked.error_code == "write_confirmation_required"
    payload = json.loads(blocked.content)
    confirmation_id = payload["confirmation_id"]

    first = await registry.confirm_and_execute(confirmation_id)
    assert first.is_error is False
    assert json.loads(first.content)["written"] == "lamp"

    second = await registry.confirm_and_execute(confirmation_id)
    assert second.is_error is True
    assert second.error_code == "invalid_or_expired_confirmation"


def test_argument_fingerprint_is_order_independent():
    left = argument_fingerprint("t", {"a": 1, "b": 2})
    right = argument_fingerprint("t", {"b": 2, "a": 1})
    assert left == right


def test_confirmation_store_expiry():
    store = WriteConfirmationStore(ttl_seconds=1)
    pending = store.create("demo.tool", {"x": 1})
    pending_expired = type(pending)(
        id=pending.id,
        tool_name=pending.tool_name,
        arguments=pending.arguments,
        fingerprint=pending.fingerprint,
        created_at=pending.created_at - timedelta(seconds=5),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    store._items[pending.id] = pending_expired
    assert store.consume(pending.id) is None


@pytest.mark.asyncio
async def test_write_confirmation_rejects_invalid_args_before_pending():
    async def handler(args: dict) -> str:
        return "ok"

    tool = RegisteredTool(
        definition=ToolDefinition(
            name="test.write",
            description="write",
            risk_level=RiskLevel.WRITE,
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string", "maxLength": 5}},
                "required": ["value"],
                "additionalProperties": False,
            },
        ),
        handler=handler,
    )
    registry = ToolRegistry()
    registry.register_module(type("M", (), {"slug": "test", "get_tools": lambda self: [tool]})())
    result = await registry.execute("test.write", {"value": "too-long-value"})
    assert result.error_code == "invalid_arguments"
