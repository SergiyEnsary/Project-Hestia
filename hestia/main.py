from __future__ import annotations

import argparse
import logging
import sys

import uvicorn

from hestia.config import load_config
from hestia.security.redact import redact


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact(original)


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def serve() -> None:
    _setup_logging()
    config = load_config()
    uvicorn.run(
        "hestia.api.app:create_app",
        factory=True,
        host=config.server.host,
        port=config.server.port,
        log_level="info",
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="hestia", description="Hestia home assistant")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="Start the Hestia API server")
    args = parser.parse_args()

    if args.command == "serve":
        serve()
    else:
        parser.print_help()
        sys.exit(1)
