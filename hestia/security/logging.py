from __future__ import annotations

import logging

from hestia.security.redact import redact


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        if record.exc_info is not None:
            exception_class = record.exc_info[0]
            exception_type = (
                exception_class.__name__ if exception_class is not None else "Exception"
            )
            record.msg = f"{record.msg} [{exception_type}]"
            record.exc_info = None
            record.exc_text = None
        return True


def install_redacting_filters() -> None:
    """Install redaction on existing application and server handlers."""
    redacting_filter = RedactingFilter()
    loggers = [
        logging.getLogger(),
        logging.getLogger("uvicorn"),
        logging.getLogger("uvicorn.access"),
        logging.getLogger("uvicorn.error"),
    ]
    for logger in loggers:
        for handler in logger.handlers:
            if not any(isinstance(item, RedactingFilter) for item in handler.filters):
                handler.addFilter(redacting_filter)
