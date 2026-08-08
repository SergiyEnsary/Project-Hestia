import logging

from hestia.security.logging import RedactingFilter
from hestia.security.redact import redact


def test_redact_bearer_token():
    msg = "Auth failed: Bearer super-secret-token-12345"
    assert "super-secret" not in redact(msg)
    assert "[REDACTED]" in redact(msg)


def test_redact_env_token():
    msg = "Loaded HESTIA_API_TOKEN=abc123 from file"
    assert "abc123" not in redact(msg)


def test_redact_ical_url():
    msg = "Failed to fetch ical/private-calendar-id/basic.ics"
    assert "private-calendar-id" not in redact(msg)


def test_redact_preserves_safe_text():
    msg = "Hestia started on 127.0.0.1:8000"
    assert redact(msg) == msg


def test_redact_full_calendar_url():
    msg = "ical_url=https://calendar.example/private-token/basic.ics"
    assert "private-token" not in redact(msg)


def test_logging_filter_redacts_formatted_arguments():
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        __file__,
        1,
        "Request used %s",
        ("Bearer secret-token",),
        None,
    )
    assert RedactingFilter().filter(record)
    assert "secret-token" not in record.getMessage()
