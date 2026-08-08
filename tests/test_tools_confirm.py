from __future__ import annotations

import json

from hestia.core.tools.models import RiskLevel, ToolDefinition
from hestia.modules.base import RegisteredTool


def test_confirm_endpoint_executes_once(client, auth_headers):
    async def handler(args: dict) -> str:
        return json.dumps({"ok": True, "n": args["n"]})

    tool = RegisteredTool(
        definition=ToolDefinition(
            name="test.write",
            description="write",
            risk_level=RiskLevel.WRITE,
            parameters={
                "type": "object",
                "properties": {"n": {"type": "integer", "minimum": 0, "maximum": 10}},
                "required": ["n"],
                "additionalProperties": False,
            },
        ),
        handler=handler,
    )
    registry = client.app.state.orchestrator._tools
    registry.register_module(type("M", (), {"slug": "test", "get_tools": lambda self: [tool]})())
    pending = registry.confirmations.create("test.write", {"n": 3})

    response = client.post(
        "/tools/confirm",
        headers=auth_headers,
        json={"confirmation_id": pending.id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["is_error"] is False
    assert json.loads(payload["content"])["n"] == 3

    again = client.post(
        "/tools/confirm",
        headers=auth_headers,
        json={"confirmation_id": pending.id},
    )
    assert again.status_code == 200
    assert again.json()["is_error"] is True


def test_confirm_requires_auth(client):
    response = client.post("/tools/confirm", json={"confirmation_id": "abcdefghijkl"})
    assert response.status_code in {401, 403}
