from __future__ import annotations

import contextvars
import uuid

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "hestia_correlation_id",
    default=None,
)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def set_correlation_id(value: str) -> contextvars.Token[str | None]:
    return _correlation_id.set(value)


def reset_correlation_id(token: contextvars.Token[str | None]) -> None:
    _correlation_id.reset(token)


def get_correlation_id() -> str:
    return _correlation_id.get() or new_correlation_id()
