import json
from datetime import UTC, datetime, timedelta

import pytest

from hestia.config import KairosConfig
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.kairos.module import KairosModule


class FakeCalendarClient:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    async def get_bytes(
        self,
        url: str,
        *,
        allowed_content_types: set[str] | None = None,
    ) -> bytes:
        assert "private-token" in url
        assert allowed_content_types and "text/calendar" in allowed_content_types
        return self.payload

    async def close(self) -> None:
        return


@pytest.mark.asyncio
async def test_kairos_lists_minimized_upcoming_events():
    start = datetime.now(UTC) + timedelta(hours=1)
    end = start + timedelta(hours=1)
    payload = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}\r\n"
        f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}\r\n"
        "SUMMARY:Private appointment\r\n"
        "LOCATION:Home\r\n"
        "DESCRIPTION:This must never be returned\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode()
    module = KairosModule()
    await module.setup(
        KairosConfig(
            enabled=True,
            ical_url="https://calendar.example/private-token/basic.ics",
        )
    )
    assert module._client is not None
    await module._client.close()
    module._client = FakeCalendarClient(payload)  # type: ignore[assignment]

    result = json.loads(await module.get_tools()[0].handler({"days": 1, "limit": 5}))
    assert len(result["events"]) == 1
    assert result["events"][0]["summary"] == "Private appointment"
    assert "description" not in result["events"][0]
    assert "must never" not in json.dumps(result)
    await module.teardown()


def test_kairos_requires_url_when_enabled():
    with pytest.raises(ValueError, match="ical_url"):
        KairosConfig(enabled=True)


@pytest.mark.asyncio
async def test_kairos_malformed_calendar_returns_safe_tool_error():
    module = KairosModule()
    await module.setup(
        KairosConfig(
            enabled=True,
            ical_url="https://calendar.example/private-token/basic.ics",
        )
    )
    assert module._client is not None
    await module._client.close()
    module._client = FakeCalendarClient(b"not a calendar")  # type: ignore[assignment]
    registry = ToolRegistry()
    registry.register_module(module)

    result = await registry.execute("kairos.list_events", {})
    assert result.is_error is True
    assert result.error_code == "tool_execution_failed"
    assert "not a calendar" not in result.content
    await module.teardown()
