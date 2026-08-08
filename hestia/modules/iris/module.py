from __future__ import annotations

import json
from typing import Any, Protocol

from hestia.config import IrisConfig, StrictConfig
from hestia.core.tools.models import RiskLevel, ToolDefinition
from hestia.modules.base import HestiaModule, RegisteredTool


class EmailSender(Protocol):
    async def send(
        self,
        *,
        from_address: str,
        to_address: str,
        subject: str,
        body: str,
    ) -> str: ...


class SesEmailSender:
    def __init__(self, *, region: str) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "Iris requires the optional 'boto3' package. "
                "Install with: pip install 'hestia[iris]'"
            ) from exc
        self._client = boto3.client("ses", region_name=region)

    async def send(
        self,
        *,
        from_address: str,
        to_address: str,
        subject: str,
        body: str,
    ) -> str:
        import asyncio

        def _send() -> str:
            response = self._client.send_email(
                Source=from_address,
                Destination={"ToAddresses": [to_address]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                },
            )
            return str(response.get("MessageId", ""))

        return await asyncio.to_thread(_send)


class IrisModule(HestiaModule):
    slug = "iris"
    display_name = "Iris"
    domain = "Email notifications via AWS SES"
    config_type = IrisConfig

    def __init__(self, sender: EmailSender | None = None) -> None:
        self._sender = sender
        self._owns_sender = sender is None
        self._from_address = ""
        self._recipient_allowlist: set[str] = set()
        self._max_subject_length = 200
        self._max_body_length = 4000
        self._region = "us-east-1"

    async def setup(self, config: StrictConfig) -> None:
        if not isinstance(config, IrisConfig):
            raise TypeError("Iris requires IrisConfig")
        self._from_address = config.from_address
        self._recipient_allowlist = {addr.lower() for addr in config.recipient_allowlist}
        self._max_subject_length = config.max_subject_length
        self._max_body_length = config.max_body_length
        self._region = config.region
        if self._sender is None:
            self._sender = SesEmailSender(region=config.region)
            self._owns_sender = True

    async def teardown(self) -> None:
        self._sender = None

    def get_tools(self) -> list[RegisteredTool]:
        return [
            RegisteredTool(
                definition=ToolDefinition(
                    name="iris.send_email",
                    description=(
                        "Send an email notification to an allowlisted recipient via SES. "
                        "Requires user confirmation."
                    ),
                    risk_level=RiskLevel.WRITE,
                    parameters={
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "minLength": 3,
                                "maxLength": 320,
                            },
                            "subject": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 500,
                            },
                            "body": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 20000,
                            },
                        },
                        "required": ["to", "subject", "body"],
                        "additionalProperties": False,
                    },
                ),
                handler=self._send_email,
            )
        ]

    async def _send_email(self, args: dict[str, Any]) -> str:
        if self._sender is None:
            raise RuntimeError("Iris is not initialized")
        to_address = str(args["to"]).strip()
        subject = str(args["subject"]).strip()
        body = str(args["body"]).strip()
        if to_address.lower() not in self._recipient_allowlist:
            raise ValueError("Recipient is not allowlisted")
        if len(subject) > self._max_subject_length:
            raise ValueError("Subject exceeds configured length limit")
        if len(body) > self._max_body_length:
            raise ValueError("Body exceeds configured length limit")
        message_id = await self._sender.send(
            from_address=self._from_address,
            to_address=to_address,
            subject=subject,
            body=body,
        )
        return json.dumps(
            {
                "to": to_address,
                "subject": subject[:80],
                "status": "sent",
                "message_id": message_id[:128],
            }
        )
