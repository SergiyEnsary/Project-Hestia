from __future__ import annotations

import json

import pytest

from hestia.config import HermesConfig
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.hermes.module import HermesModule


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bytes, int, bool]] = []

    async def publish(self, topic: str, payload: bytes, *, qos: int, retain: bool) -> None:
        self.messages.append((topic, payload, qos, retain))

    async def close(self) -> None:
        return


@pytest.mark.asyncio
async def test_hermes_publish_requires_confirmation_and_allowlist():
    publisher = FakePublisher()
    module = HermesModule(publisher=publisher)
    await module.setup(
        HermesConfig(
            enabled=True,
            topic_allowlist=["home/hestia/#", "alerts/test"],
        )
    )
    registry = ToolRegistry()
    registry.register_module(module)

    blocked = await registry.execute(
        "hermes.publish",
        {"topic": "home/hestia/status", "payload": "online", "qos": 0, "retain": False},
    )
    assert blocked.error_code == "write_confirmation_required"
    result = await registry.confirm_and_execute(json.loads(blocked.content)["confirmation_id"])
    assert result.is_error is False
    assert publisher.messages[0][0] == "home/hestia/status"

    denied = await registry.execute(
        "hermes.publish",
        {"topic": "evil/topic", "payload": "nope"},
    )
    confirmed = await registry.confirm_and_execute(json.loads(denied.content)["confirmation_id"])
    assert confirmed.is_error is True
    await module.teardown()


def test_hermes_requires_topic_allowlist_when_enabled():
    with pytest.raises(ValueError, match="topic_allowlist"):
        HermesConfig(enabled=True)
