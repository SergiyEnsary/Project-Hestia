from __future__ import annotations

import hashlib
import json
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


def _canonical_arguments(arguments: dict[str, Any]) -> str:
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)


def argument_fingerprint(tool_name: str, arguments: dict[str, Any]) -> str:
    payload = f"{tool_name}:{_canonical_arguments(arguments)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PendingConfirmation:
    id: str
    tool_name: str
    arguments: dict[str, Any]
    fingerprint: str
    created_at: datetime
    expires_at: datetime


class WriteConfirmationStore:
    """In-memory one-use write confirmations bound to exact tool arguments."""

    def __init__(self, *, ttl_seconds: int = 120) -> None:
        if ttl_seconds < 1 or ttl_seconds > 3600:
            raise ValueError("ttl_seconds must be between 1 and 3600")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._items: dict[str, PendingConfirmation] = {}
        self._lock = threading.RLock()

    def create(self, tool_name: str, arguments: dict[str, Any]) -> PendingConfirmation:
        now = datetime.now(UTC)
        pending = PendingConfirmation(
            id=secrets.token_urlsafe(24),
            tool_name=tool_name,
            arguments=dict(arguments),
            fingerprint=argument_fingerprint(tool_name, arguments),
            created_at=now,
            expires_at=now + self._ttl,
        )
        with self._lock:
            self._prune_locked(now)
            self._items[pending.id] = pending
        return pending

    def peek(self, confirmation_id: str) -> PendingConfirmation | None:
        with self._lock:
            self._prune_locked(datetime.now(UTC))
            return self._items.get(confirmation_id)

    def consume(
        self,
        confirmation_id: str,
        *,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> PendingConfirmation | None:
        """Consume a confirmation once. Optional exact name/args binding for defense in depth."""
        with self._lock:
            now = datetime.now(UTC)
            self._prune_locked(now)
            pending = self._items.pop(confirmation_id, None)
            if pending is None:
                return None
            if pending.expires_at <= now:
                return None
            if tool_name is not None and pending.tool_name != tool_name:
                return None
            if arguments is not None:
                expected = argument_fingerprint(pending.tool_name, arguments)
                if pending.fingerprint != expected:
                    return None
            return pending

    def _prune_locked(self, now: datetime) -> None:
        expired = [key for key, item in self._items.items() if item.expires_at <= now]
        for key in expired:
            del self._items[key]
