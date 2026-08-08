from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hestia.config import MnemosyneConfig
from hestia.core.tools.models import ChatMessage


@dataclass
class Session:
    id: str
    messages: list[ChatMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SessionRepository(ABC):
    @abstractmethod
    def get_or_create(self, session_id: str | None) -> Session:
        pass

    @abstractmethod
    def add_message(self, session_id: str, message: ChatMessage) -> None:
        pass

    @abstractmethod
    def get_messages(self, session_id: str) -> list[ChatMessage]:
        pass

    @abstractmethod
    def delete(self, session_id: str) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class InMemorySessionRepository(SessionRepository):
    def __init__(self, *, max_messages: int, retention_days: int) -> None:
        self._max_messages = max_messages
        self._retention = timedelta(days=retention_days)
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def _prune_expired(self) -> None:
        cutoff = datetime.now(UTC) - self._retention
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.updated_at < cutoff
        ]
        for session_id in expired:
            del self._sessions[session_id]

    def get_or_create(self, session_id: str | None) -> Session:
        with self._lock:
            self._prune_expired()
            if session_id and session_id in self._sessions:
                return self._sessions[session_id]
            new_id = session_id or str(uuid.uuid4())
            session = Session(id=new_id)
            self._sessions[new_id] = session
            return session

    def add_message(self, session_id: str, message: ChatMessage) -> None:
        with self._lock:
            session = self.get_or_create(session_id)
            session.messages.append(message)
            if len(session.messages) > self._max_messages:
                session.messages = session.messages[-self._max_messages :]
            session.updated_at = datetime.now(UTC)

    def get_messages(self, session_id: str) -> list[ChatMessage]:
        with self._lock:
            return list(self.get_or_create(session_id).messages)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def close(self) -> None:
        return


class SQLiteSessionRepository(SessionRepository):
    def __init__(
        self,
        path: Path,
        *,
        max_messages: int,
        retention_days: int,
    ) -> None:
        self._max_messages = max_messages
        self._retention = timedelta(days=retention_days)
        self._lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        os.chmod(path, 0o600)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        try:
            self._migrate()
        except Exception:
            self._connection.close()
            raise

    def _migrate(self) -> None:
        with self._connection:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("Mnemosyne database is newer than this Hestia version")
            if version == 0:
                self._connection.executescript(
                    """
                    CREATE TABLE sessions (
                        id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX messages_session_id_idx
                        ON messages(session_id, id);
                    PRAGMA user_version = 1;
                    """
                )

    def _prune_expired(self) -> None:
        cutoff = (datetime.now(UTC) - self._retention).isoformat()
        self._connection.execute(
            "DELETE FROM sessions WHERE updated_at < ?",
            (cutoff,),
        )

    def get_or_create(self, session_id: str | None) -> Session:
        with self._lock, self._connection:
            self._prune_expired()
            if session_id:
                row = self._connection.execute(
                    "SELECT id, created_at, updated_at FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
                if row is not None:
                    return self._row_to_session(row)
            new_id = session_id or str(uuid.uuid4())
            now = datetime.now(UTC).isoformat()
            self._connection.execute(
                "INSERT INTO sessions(id, created_at, updated_at) VALUES (?, ?, ?)",
                (new_id, now, now),
            )
            return Session(
                id=new_id,
                created_at=datetime.fromisoformat(now),
                updated_at=datetime.fromisoformat(now),
            )

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        messages = self.get_messages(str(row["id"]))
        return Session(
            id=str(row["id"]),
            messages=messages,
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )

    def add_message(self, session_id: str, message: ChatMessage) -> None:
        with self._lock:
            self.get_or_create(session_id)
            with self._connection:
                now = datetime.now(UTC).isoformat()
                self._connection.execute(
                    """
                    INSERT INTO messages(session_id, payload, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (session_id, message.model_dump_json(), now),
                )
                self._connection.execute(
                    "UPDATE sessions SET updated_at = ? WHERE id = ?",
                    (now, session_id),
                )
                self._connection.execute(
                    """
                    DELETE FROM messages
                    WHERE session_id = ? AND id NOT IN (
                        SELECT id FROM messages
                        WHERE session_id = ?
                        ORDER BY id DESC LIMIT ?
                    )
                    """,
                    (session_id, session_id, self._max_messages),
                )

    def get_messages(self, session_id: str) -> list[ChatMessage]:
        with self._lock, self._connection:
            self._prune_expired()
            rows = self._connection.execute(
                "SELECT payload FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            return [ChatMessage.model_validate_json(str(row["payload"])) for row in rows]

    def delete(self, session_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,),
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class Mnemosyne:
    """Bounded session memory backed by an interchangeable repository."""

    def __init__(self, config: MnemosyneConfig | None = None) -> None:
        config = config or MnemosyneConfig()
        if config.backend == "sqlite":
            self._repository: SessionRepository = SQLiteSessionRepository(
                config.database_path,
                max_messages=config.max_messages_per_session,
                retention_days=config.retention_days,
            )
        else:
            self._repository = InMemorySessionRepository(
                max_messages=config.max_messages_per_session,
                retention_days=config.retention_days,
            )

    def get_or_create(self, session_id: str | None) -> Session:
        return self._repository.get_or_create(session_id)

    def add_message(self, session_id: str, message: ChatMessage) -> None:
        self._repository.add_message(session_id, message)

    def get_messages(self, session_id: str) -> list[ChatMessage]:
        return self._repository.get_messages(session_id)

    def clear(self, session_id: str) -> None:
        self._repository.delete(session_id)

    def close(self) -> None:
        self._repository.close()
