from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from icalendar import Calendar

from hestia.config import KairosConfig, StrictConfig
from hestia.core.tools.models import RiskLevel, ToolDefinition
from hestia.modules.base import HestiaModule, RegisteredTool
from hestia.security.http import SecureHTTPClient


class KairosModule(HestiaModule):
    slug = "kairos"
    display_name = "Kairos"
    domain = "Read-only calendar events"
    config_type = KairosConfig

    def __init__(self) -> None:
        self._ical_url = ""
        self._client: SecureHTTPClient | None = None

    async def setup(self, config: StrictConfig) -> None:
        if not isinstance(config, KairosConfig):
            raise TypeError("Kairos requires KairosConfig")
        self._ical_url = config.ical_url
        self._client = SecureHTTPClient(
            timeout_seconds=config.timeout_seconds,
            max_response_bytes=config.max_response_bytes,
            allow_private_hosts=config.allow_private_hosts,
        )

    async def teardown(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    def get_tools(self) -> list[RegisteredTool]:
        return [
            RegisteredTool(
                definition=ToolDefinition(
                    name="kairos.list_events",
                    description="List upcoming calendar events from the configured calendar.",
                    risk_level=RiskLevel.READ,
                    parameters={
                        "type": "object",
                        "properties": {
                            "days": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 31,
                                "default": 7,
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 20,
                            },
                        },
                        "additionalProperties": False,
                    },
                ),
                handler=self._list_events,
            )
        ]

    async def _list_events(self, args: dict[str, Any]) -> str:
        if self._client is None:
            raise RuntimeError("Kairos is not initialized")
        days = int(args.get("days", 7))
        limit = int(args.get("limit", 20))
        payload = await self._client.get_bytes(
            self._ical_url,
            allowed_content_types={
                "text/calendar",
                "text/plain",
                "application/octet-stream",
            },
        )
        calendar = Calendar.from_ical(payload)
        now = datetime.now(UTC)
        cutoff = now + timedelta(days=days)
        events: list[dict[str, str | None]] = []

        for index, component in enumerate(calendar.walk("VEVENT")):
            if index >= 5000:
                break
            start = self._as_datetime(component.decoded("dtstart"))
            if start < now or start > cutoff:
                continue
            end_value = component.decoded("dtend") if component.get("dtend") else None
            end = self._as_datetime(end_value) if end_value is not None else None
            events.append(
                {
                    "summary": self._safe_text(component.get("summary"), 300),
                    "start": start.isoformat(),
                    "end": end.isoformat() if end else None,
                    "location": self._safe_text(component.get("location"), 300),
                }
            )

        events.sort(key=lambda event: event["start"] or "")
        return json.dumps({"events": events[:limit]})

    @staticmethod
    def _as_datetime(value: date | datetime) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        return datetime.combine(value, time.min, tzinfo=UTC)

    @staticmethod
    def _safe_text(value: object | None, max_length: int) -> str | None:
        if value is None:
            return None
        return str(value).replace("\r", " ").replace("\n", " ").strip()[:max_length]
