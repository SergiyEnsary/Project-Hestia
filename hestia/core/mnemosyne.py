from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from hestia.core.tools.models import ChatMessage


@dataclass
class Session:
    id: str
    messages: list[ChatMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Mnemosyne:
    """In-memory session store."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str | None) -> Session:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        new_id = session_id or str(uuid.uuid4())
        session = Session(id=new_id)
        self._sessions[new_id] = session
        return session

    def add_message(self, session_id: str, message: ChatMessage) -> None:
        session = self.get_or_create(session_id)
        session.messages.append(message)
        session.updated_at = datetime.now(timezone.utc)

    def get_messages(self, session_id: str) -> list[ChatMessage]:
        return list(self.get_or_create(session_id).messages)

    def clear(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]
