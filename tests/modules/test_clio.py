from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from hestia.config import ClioConfig
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.clio.module import ClioModule


@pytest.mark.asyncio
async def test_clio_create_list_complete_delete(tmp_path):
    module = ClioModule()
    await module.setup(
        ClioConfig(enabled=True, database_path=tmp_path / "clio.db", max_reminders=10)
    )
    registry = ToolRegistry()
    registry.register_module(module)

    blocked = await registry.execute(
        "clio.create_reminder",
        {"title": "Buy milk", "body": "2%", "due_at": ""},
    )
    assert blocked.error_code == "write_confirmation_required"
    confirmation_id = json.loads(blocked.content)["confirmation_id"]
    created = await registry.confirm_and_execute(confirmation_id)
    assert created.is_error is False
    reminder_id = json.loads(created.content)["id"]

    listed = json.loads(await module.get_tools()[0].handler({"status": "open", "limit": 10}))
    assert listed["reminders"][0]["title"] == "Buy milk"

    complete_blocked = await registry.execute(
        "clio.complete_reminder", {"reminder_id": reminder_id}
    )
    completed = await registry.confirm_and_execute(
        json.loads(complete_blocked.content)["confirmation_id"]
    )
    assert json.loads(completed.content)["status"] == "completed"

    delete_blocked = await registry.execute("clio.delete_reminder", {"reminder_id": reminder_id})
    deleted = await registry.confirm_and_execute(
        json.loads(delete_blocked.content)["confirmation_id"]
    )
    assert json.loads(deleted.content)["deleted"] is True
    await module.teardown()


@pytest.mark.asyncio
async def test_clio_rejects_invalid_due_at(tmp_path):
    module = ClioModule()
    await module.setup(ClioConfig(enabled=True, database_path=tmp_path / "clio.db"))
    registry = ToolRegistry()
    registry.register_module(module)
    blocked = await registry.execute(
        "clio.create_reminder",
        {"title": "X", "due_at": "not-a-date"},
    )
    confirmed = await registry.confirm_and_execute(json.loads(blocked.content)["confirmation_id"])
    assert confirmed.is_error is True
    assert confirmed.error_code == "tool_execution_failed"
    await module.teardown()


@pytest.mark.asyncio
async def test_clio_enforces_capacity(tmp_path):
    module = ClioModule()
    await module.setup(
        ClioConfig(enabled=True, database_path=tmp_path / "clio.db", max_reminders=1)
    )
    registry = ToolRegistry()
    registry.register_module(module)
    first = await registry.execute("clio.create_reminder", {"title": "one"})
    await registry.confirm_and_execute(json.loads(first.content)["confirmation_id"])
    second = await registry.execute("clio.create_reminder", {"title": "two"})
    result = await registry.confirm_and_execute(json.loads(second.content)["confirmation_id"])
    assert result.is_error is True
    await module.teardown()


@pytest.mark.asyncio
async def test_clio_parses_iso_due(tmp_path):
    module = ClioModule()
    await module.setup(ClioConfig(enabled=True, database_path=tmp_path / "clio.db"))
    due = (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0).isoformat()
    result = json.loads(
        await module.get_tools()[1].handler({"title": "Soon", "due_at": due})
    )
    assert result["due_at"] is not None
    await module.teardown()
