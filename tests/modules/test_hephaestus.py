from __future__ import annotations

import json

import httpx
import pytest

from hestia.config import HephaestusConfig
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.hephaestus.module import HephaestusModule


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, routes: dict[tuple[str, str], httpx.Response]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        key = (request.method, request.url.path)
        if key not in self.routes:
            return httpx.Response(404, json={"message": "missing"})
        return self.routes[key]


async def _ready_module(transport: FakeTransport) -> HephaestusModule:
    module = HephaestusModule()
    await module.setup(
        HephaestusConfig(
            enabled=True,
            base_url="http://127.0.0.1:8123",
            access_token="token-value",
            allow_insecure_http=True,
            entity_allowlist=["light.*"],
            service_allowlist=["light.turn_on"],
        )
    )
    await module._client.aclose()
    module._client = httpx.AsyncClient(
        transport=transport,
        headers={"Authorization": "Bearer token-value"},
    )
    return module


@pytest.mark.asyncio
async def test_hephaestus_read_and_confirmed_write():
    transport = FakeTransport(
        {
            ("GET", "/api/states/light.kitchen"): httpx.Response(
                200,
                json={
                    "entity_id": "light.kitchen",
                    "state": "off",
                    "attributes": {"friendly_name": "Kitchen"},
                    "last_changed": "2026-01-01T00:00:00+00:00",
                },
            ),
            ("GET", "/api/states"): httpx.Response(
                200,
                json=[
                    {
                        "entity_id": "light.kitchen",
                        "state": "off",
                        "attributes": {"friendly_name": "Kitchen"},
                    },
                    {
                        "entity_id": "lock.front",
                        "state": "locked",
                        "attributes": {"friendly_name": "Front"},
                    },
                ],
            ),
            ("POST", "/api/services/light/turn_on"): httpx.Response(200, json=[]),
        }
    )
    module = await _ready_module(transport)

    state = json.loads(await module.get_tools()[0].handler({"entity_id": "light.kitchen"}))
    assert state["state"] == "off"
    assert state["friendly_name"] == "Kitchen"

    listed = json.loads(await module.get_tools()[1].handler({"limit": 10}))
    assert len(listed["states"]) == 1

    registry = ToolRegistry()
    registry.register_module(module)
    denied = await registry.execute(
        "hephaestus.call_service",
        {"domain": "light", "service": "turn_on", "entity_id": "light.kitchen"},
    )
    assert denied.error_code == "write_confirmation_required"
    confirmed = await registry.confirm_and_execute(json.loads(denied.content)["confirmation_id"])
    assert confirmed.is_error is False
    assert ("POST", "/api/services/light/turn_on") in transport.calls
    await module.teardown()


@pytest.mark.asyncio
async def test_hephaestus_blocks_non_allowlisted_entity():
    module = await _ready_module(FakeTransport({}))
    with pytest.raises(ValueError, match="allowlisted"):
        await module.get_tools()[0].handler({"entity_id": "lock.front"})
    await module.teardown()


def test_hephaestus_requires_allowlists_when_enabled():
    with pytest.raises(ValueError, match="entity_allowlist"):
        HephaestusConfig(
            enabled=True,
            base_url="https://ha.example",
            access_token="token",
            service_allowlist=["light.turn_on"],
        )
