from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from hestia.config import HermesConfig, StrictConfig
from hestia.core.tools.models import RiskLevel, ToolDefinition
from hestia.modules.base import HestiaModule, RegisteredTool


class MqttPublisher(Protocol):
    async def publish(self, topic: str, payload: bytes, *, qos: int, retain: bool) -> None: ...

    async def close(self) -> None: ...


class PahoMqttPublisher:
    """Lazy paho-mqtt publisher used when Hermes is enabled."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        use_tls: bool,
        username: str,
        password: str,
        client_id: str,
        timeout_seconds: float,
    ) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError(
                "Hermes requires the optional 'paho-mqtt' package. "
                "Install with: pip install 'hestia[hermes]'"
            ) from exc
        self._mqtt = mqtt
        self._host = host
        self._port = port
        self._use_tls = use_tls
        self._username = username
        self._password = password
        self._client_id = client_id
        self._timeout = timeout_seconds
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        client = self._mqtt.Client(client_id=self._client_id, protocol=self._mqtt.MQTTv311)
        if self._username:
            client.username_pw_set(self._username, self._password or None)
        if self._use_tls:
            client.tls_set()
        self._client = client
        return client

    async def publish(self, topic: str, payload: bytes, *, qos: int, retain: bool) -> None:
        client = self._ensure_client()

        def _publish() -> None:
            info = client.connect(self._host, self._port, keepalive=30)
            if info != self._mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError("MQTT connect failed")
            client.loop_start()
            try:
                result = client.publish(topic, payload, qos=qos, retain=retain)
                result.wait_for_publish(timeout=self._timeout)
                if not result.is_published():
                    raise RuntimeError("MQTT publish failed")
            finally:
                client.loop_stop()
                client.disconnect()

        await asyncio.to_thread(_publish)

    async def close(self) -> None:
        self._client = None


class HermesModule(HestiaModule):
    slug = "hermes"
    display_name = "Hermes"
    domain = "MQTT messaging on allowlisted topics"
    config_type = HermesConfig

    def __init__(self, publisher: MqttPublisher | None = None) -> None:
        self._publisher = publisher
        self._owns_publisher = publisher is None
        self._topic_allowlist: list[str] = []
        self._max_payload_bytes = 8192
        self._config: HermesConfig | None = None

    async def setup(self, config: StrictConfig) -> None:
        if not isinstance(config, HermesConfig):
            raise TypeError("Hermes requires HermesConfig")
        self._config = config
        self._topic_allowlist = list(config.topic_allowlist)
        self._max_payload_bytes = config.max_payload_bytes
        if self._publisher is None:
            self._publisher = PahoMqttPublisher(
                host=config.host,
                port=config.port,
                use_tls=config.use_tls,
                username=config.username,
                password=config.password,
                client_id=config.client_id,
                timeout_seconds=float(config.timeout_seconds),
            )
            self._owns_publisher = True

    async def teardown(self) -> None:
        if self._publisher is not None and self._owns_publisher:
            await self._publisher.close()
        self._publisher = None

    def get_tools(self) -> list[RegisteredTool]:
        return [
            RegisteredTool(
                definition=ToolDefinition(
                    name="hermes.publish",
                    description=(
                        "Publish a message to an allowlisted MQTT topic. "
                        "Requires user confirmation."
                    ),
                    risk_level=RiskLevel.WRITE,
                    parameters={
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 256,
                            },
                            "payload": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 8192,
                            },
                            "qos": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 1,
                            },
                            "retain": {
                                "type": "boolean",
                            },
                        },
                        "required": ["topic", "payload"],
                        "additionalProperties": False,
                    },
                ),
                handler=self._publish,
            )
        ]

    def _topic_allowed(self, topic: str) -> bool:
        for pattern in self._topic_allowlist:
            if pattern.endswith("/#"):
                if topic.startswith(pattern[:-1]) or topic == pattern[:-2]:
                    return True
            elif pattern.endswith("*"):
                if topic.startswith(pattern[:-1]):
                    return True
            elif topic == pattern:
                return True
        return False

    async def _publish(self, args: dict[str, Any]) -> str:
        if self._publisher is None:
            raise RuntimeError("Hermes is not initialized")
        topic = str(args["topic"]).strip()
        payload = str(args["payload"])
        qos = int(args.get("qos", 0))
        retain = bool(args.get("retain", False))
        if not self._topic_allowed(topic):
            raise ValueError("Topic is not allowlisted")
        encoded = payload.encode("utf-8")
        if len(encoded) > self._max_payload_bytes:
            raise ValueError("Payload exceeds configured size limit")
        await self._publisher.publish(topic, encoded, qos=qos, retain=retain)
        return json.dumps(
            {
                "topic": topic,
                "bytes": len(encoded),
                "qos": qos,
                "retain": retain,
                "status": "published",
            }
        )
