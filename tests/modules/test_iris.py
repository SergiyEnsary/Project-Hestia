from __future__ import annotations

import json

import pytest

from hestia.config import IrisConfig
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.iris.module import IrisModule


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(
        self,
        *,
        from_address: str,
        to_address: str,
        subject: str,
        body: str,
    ) -> str:
        self.sent.append(
            {
                "from": from_address,
                "to": to_address,
                "subject": subject,
                "body": body,
            }
        )
        return "msg-123"


@pytest.mark.asyncio
async def test_iris_send_email_with_confirmation():
    sender = FakeSender()
    module = IrisModule(sender=sender)
    await module.setup(
        IrisConfig(
            enabled=True,
            from_address="hestia@example.com",
            recipient_allowlist=["you@example.com"],
        )
    )
    registry = ToolRegistry()
    registry.register_module(module)

    blocked = await registry.execute(
        "iris.send_email",
        {
            "to": "you@example.com",
            "subject": "Reminder",
            "body": "Dinner at 7",
        },
    )
    assert blocked.error_code == "write_confirmation_required"
    result = await registry.confirm_and_execute(json.loads(blocked.content)["confirmation_id"])
    assert result.is_error is False
    assert sender.sent[0]["to"] == "you@example.com"
    await module.teardown()


@pytest.mark.asyncio
async def test_iris_rejects_non_allowlisted_recipient():
    module = IrisModule(sender=FakeSender())
    await module.setup(
        IrisConfig(
            enabled=True,
            from_address="hestia@example.com",
            recipient_allowlist=["you@example.com"],
        )
    )
    registry = ToolRegistry()
    registry.register_module(module)
    blocked = await registry.execute(
        "iris.send_email",
        {"to": "evil@example.com", "subject": "x", "body": "y"},
    )
    result = await registry.confirm_and_execute(json.loads(blocked.content)["confirmation_id"])
    assert result.is_error is True
    await module.teardown()


def test_iris_requires_recipients_when_enabled():
    with pytest.raises(ValueError, match="recipient_allowlist"):
        IrisConfig(enabled=True, from_address="hestia@example.com")
