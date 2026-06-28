from __future__ import annotations

import re
from typing import Pattern

SENSITIVE_PATTERNS: list[Pattern[str]] = [
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"HESTIA_API_TOKEN=\S+"),
    re.compile(r"ical/[^/\s]+", re.IGNORECASE),
    re.compile(r"https?://[^@\s]+@[^\s]+"),
]


def redact(message: str) -> str:
    redacted = message
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted
