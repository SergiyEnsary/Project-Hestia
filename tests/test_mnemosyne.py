import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from hestia.config import MnemosyneConfig
from hestia.core.mnemosyne import Mnemosyne
from hestia.core.tools.models import ChatMessage


@pytest.fixture
def memory() -> Mnemosyne:
    return Mnemosyne()


def test_creates_new_session(memory):
    session = memory.get_or_create(None)
    assert session.id
    uuid.UUID(session.id)


def test_reuses_existing_session(memory):
    session = memory.get_or_create(None)
    same = memory.get_or_create(session.id)
    assert same.id == session.id


def test_add_and_get_messages(memory):
    session = memory.get_or_create(None)
    memory.add_message(session.id, ChatMessage(role="user", content="Hello"))
    messages = memory.get_messages(session.id)
    assert len(messages) == 1
    assert messages[0].content == "Hello"


def test_clear_session(memory):
    session = memory.get_or_create(None)
    memory.add_message(session.id, ChatMessage(role="user", content="Hi"))
    memory.clear(session.id)
    assert memory.get_messages(session.id) == []


def test_bounds_session_history():
    memory = Mnemosyne(MnemosyneConfig(max_messages_per_session=2))
    session = memory.get_or_create(None)
    for index in range(3):
        memory.add_message(
            session.id,
            ChatMessage(role="user", content=f"message-{index}"),
        )
    assert [message.content for message in memory.get_messages(session.id)] == [
        "message-1",
        "message-2",
    ]


def test_sqlite_persists_and_deletes_sessions(tmp_path):
    database_path = tmp_path / "data" / "mnemosyne.db"
    config = MnemosyneConfig(backend="sqlite", database_path=database_path)
    memory = Mnemosyne(config)
    session = memory.get_or_create(None)
    memory.add_message(session.id, ChatMessage(role="user", content="private"))
    memory.close()

    reopened = Mnemosyne(config)
    assert reopened.get_messages(session.id)[0].content == "private"
    reopened.clear(session.id)
    assert reopened.get_messages(session.id) == []
    reopened.close()
    assert database_path.stat().st_mode & 0o777 == 0o600


def test_sqlite_rejects_unknown_future_migration(tmp_path):
    database_path = tmp_path / "future.db"
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA user_version = 999")
    connection.close()
    with pytest.raises(RuntimeError, match="newer"):
        Mnemosyne(
            MnemosyneConfig(
                backend="sqlite",
                database_path=database_path,
            )
        )


def test_sqlite_serializes_concurrent_writes(tmp_path):
    memory = Mnemosyne(
        MnemosyneConfig(
            backend="sqlite",
            database_path=tmp_path / "concurrent.db",
            max_messages_per_session=50,
        )
    )
    session = memory.get_or_create(None)

    def write(index: int) -> None:
        memory.add_message(
            session.id,
            ChatMessage(role="user", content=f"message-{index}"),
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(write, range(20)))

    assert len(memory.get_messages(session.id)) == 20
    memory.close()


def test_sqlite_prunes_expired_sessions(tmp_path):
    database_path = tmp_path / "retention.db"
    config = MnemosyneConfig(
        backend="sqlite",
        database_path=database_path,
        retention_days=1,
    )
    memory = Mnemosyne(config)
    session = memory.get_or_create(None)
    memory.add_message(session.id, ChatMessage(role="user", content="expired"))
    memory.close()

    connection = sqlite3.connect(database_path)
    connection.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        ("2000-01-01T00:00:00+00:00", session.id),
    )
    connection.commit()
    connection.close()

    reopened = Mnemosyne(config)
    assert reopened.get_messages(session.id) == []
    reopened.close()
