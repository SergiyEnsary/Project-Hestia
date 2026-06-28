import uuid

import pytest

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
