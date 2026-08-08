from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from hestia.config import ClioConfig, StrictConfig
from hestia.core.tools.models import RiskLevel, ToolDefinition
from hestia.modules.base import HestiaModule, RegisteredTool


class ClioModule(HestiaModule):
    slug = "clio"
    display_name = "Clio"
    domain = "Reminders and notes"
    config_type = ClioConfig

    def __init__(self) -> None:
        self._path: Path | None = None
        self._retention_days = 365
        self._max_reminders = 500
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    async def setup(self, config: StrictConfig) -> None:
        if not isinstance(config, ClioConfig):
            raise TypeError("Clio requires ClioConfig")
        self._path = config.database_path
        self._retention_days = config.retention_days
        self._max_reminders = config.max_reminders
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                due_at TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
        self._prune_completed()

    async def teardown(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def get_tools(self) -> list[RegisteredTool]:
        return [
            RegisteredTool(
                definition=ToolDefinition(
                    name="clio.list_reminders",
                    description="List reminders, optionally filtered by status.",
                    risk_level=RiskLevel.READ,
                    parameters={
                        "type": "object",
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["open", "completed", "all"],
                                "maxLength": 16,
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                            },
                        },
                        "additionalProperties": False,
                    },
                ),
                handler=self._list_reminders,
            ),
            RegisteredTool(
                definition=ToolDefinition(
                    name="clio.create_reminder",
                    description="Create a reminder or note. Requires user confirmation.",
                    risk_level=RiskLevel.WRITE,
                    parameters={
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                            },
                            "body": {
                                "type": "string",
                                "maxLength": 2000,
                            },
                            "due_at": {
                                "type": "string",
                                "description": "ISO-8601 due timestamp, or empty if none",
                                "maxLength": 64,
                            },
                        },
                        "required": ["title"],
                        "additionalProperties": False,
                    },
                ),
                handler=self._create_reminder,
            ),
            RegisteredTool(
                definition=ToolDefinition(
                    name="clio.complete_reminder",
                    description="Mark a reminder completed. Requires user confirmation.",
                    risk_level=RiskLevel.WRITE,
                    parameters={
                        "type": "object",
                        "properties": {
                            "reminder_id": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 64,
                            },
                        },
                        "required": ["reminder_id"],
                        "additionalProperties": False,
                    },
                ),
                handler=self._complete_reminder,
            ),
            RegisteredTool(
                definition=ToolDefinition(
                    name="clio.delete_reminder",
                    description="Delete a reminder. Requires user confirmation.",
                    risk_level=RiskLevel.WRITE,
                    parameters={
                        "type": "object",
                        "properties": {
                            "reminder_id": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 64,
                            },
                        },
                        "required": ["reminder_id"],
                        "additionalProperties": False,
                    },
                ),
                handler=self._delete_reminder,
            ),
        ]

    async def _list_reminders(self, args: dict[str, Any]) -> str:
        status = args.get("status", "open")
        limit = int(args.get("limit", 20))
        with self._lock:
            assert self._conn is not None
            if status == "all":
                rows = self._conn.execute(
                    """
                    SELECT id, title, body, due_at, status, created_at, updated_at
                    FROM reminders
                    ORDER BY COALESCE(due_at, created_at) ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT id, title, body, due_at, status, created_at, updated_at
                    FROM reminders
                    WHERE status = ?
                    ORDER BY COALESCE(due_at, created_at) ASC
                    LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
        return json.dumps({"reminders": [dict(row) for row in rows]})

    async def _create_reminder(self, args: dict[str, Any]) -> str:
        title = str(args["title"]).strip()
        body = str(args.get("body", "")).strip()
        due_raw = str(args.get("due_at", "")).strip()
        due_at = self._parse_due(due_raw) if due_raw else None
        now = datetime.now(UTC).isoformat()
        reminder_id = str(uuid.uuid4())
        with self._lock:
            assert self._conn is not None
            count = self._conn.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]
            if count >= self._max_reminders:
                raise ValueError("Reminder capacity reached")
            self._conn.execute(
                """
                INSERT INTO reminders (id, title, body, due_at, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'open', ?, ?)
                """,
                (reminder_id, title, body, due_at, now, now),
            )
            self._conn.commit()
        return json.dumps(
            {
                "id": reminder_id,
                "title": title,
                "body": body,
                "due_at": due_at,
                "status": "open",
            }
        )

    async def _complete_reminder(self, args: dict[str, Any]) -> str:
        reminder_id = str(args["reminder_id"]).strip()
        now = datetime.now(UTC).isoformat()
        with self._lock:
            assert self._conn is not None
            cursor = self._conn.execute(
                """
                UPDATE reminders
                SET status = 'completed', updated_at = ?
                WHERE id = ? AND status = 'open'
                """,
                (now, reminder_id),
            )
            self._conn.commit()
            if cursor.rowcount != 1:
                raise ValueError("Reminder not found or already completed")
        return json.dumps({"id": reminder_id, "status": "completed"})

    async def _delete_reminder(self, args: dict[str, Any]) -> str:
        reminder_id = str(args["reminder_id"]).strip()
        with self._lock:
            assert self._conn is not None
            cursor = self._conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            self._conn.commit()
            if cursor.rowcount != 1:
                raise ValueError("Reminder not found")
        return json.dumps({"id": reminder_id, "deleted": True})

    def _prune_completed(self) -> None:
        assert self._conn is not None
        cutoff = (datetime.now(UTC) - timedelta(days=self._retention_days)).isoformat()
        with self._lock:
            self._conn.execute(
                """
                DELETE FROM reminders
                WHERE status = 'completed' AND updated_at < ?
                """,
                (cutoff,),
            )
            self._conn.commit()

    @staticmethod
    def _parse_due(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("due_at must be a valid ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()
