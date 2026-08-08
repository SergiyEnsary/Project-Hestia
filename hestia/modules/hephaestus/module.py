from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from typing import Any
from urllib.parse import urlsplit

import httpx

from hestia.config import HephaestusConfig, StrictConfig
from hestia.core.tools.models import RiskLevel, ToolDefinition
from hestia.modules.base import HestiaModule, RegisteredTool
from hestia.security.http import UnsafeOutboundURLError


class HephaestusModule(HestiaModule):
    slug = "hephaestus"
    display_name = "Hephaestus"
    domain = "Smart home device state and control via Home Assistant"
    config_type = HephaestusConfig

    def __init__(self) -> None:
        self._base_url = ""
        self._token = ""
        self._timeout = 15.0
        self._max_response_bytes = 1_000_000
        self._allow_private_hosts = True
        self._allow_insecure_http = False
        self._entity_allowlist: list[str] = []
        self._service_allowlist: list[str] = []
        self._client: httpx.AsyncClient | None = None

    async def setup(self, config: StrictConfig) -> None:
        if not isinstance(config, HephaestusConfig):
            raise TypeError("Hephaestus requires HephaestusConfig")
        self._base_url = config.base_url.rstrip("/")
        self._token = config.access_token
        self._timeout = float(config.timeout_seconds)
        self._max_response_bytes = config.max_response_bytes
        self._allow_private_hosts = config.allow_private_hosts
        self._allow_insecure_http = config.allow_insecure_http
        self._entity_allowlist = list(config.entity_allowlist)
        self._service_allowlist = list(config.service_allowlist)
        await self._validate_base_url(self._base_url)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=False,
            trust_env=False,
            headers={"Authorization": f"Bearer {self._token}"},
        )

    async def teardown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def get_tools(self) -> list[RegisteredTool]:
        return [
            RegisteredTool(
                definition=ToolDefinition(
                    name="hephaestus.get_state",
                    description="Get the state of an allowlisted Home Assistant entity.",
                    risk_level=RiskLevel.READ,
                    parameters={
                        "type": "object",
                        "properties": {
                            "entity_id": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                            },
                        },
                        "required": ["entity_id"],
                        "additionalProperties": False,
                    },
                ),
                handler=self._get_state,
            ),
            RegisteredTool(
                definition=ToolDefinition(
                    name="hephaestus.list_states",
                    description="List states for allowlisted Home Assistant entities.",
                    risk_level=RiskLevel.READ,
                    parameters={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                            },
                        },
                        "additionalProperties": False,
                    },
                ),
                handler=self._list_states,
            ),
            RegisteredTool(
                definition=ToolDefinition(
                    name="hephaestus.call_service",
                    description=(
                        "Call an allowlisted Home Assistant service on an allowlisted entity. "
                        "Requires user confirmation."
                    ),
                    risk_level=RiskLevel.WRITE,
                    parameters={
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 64,
                            },
                            "service": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 64,
                            },
                            "entity_id": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                            },
                        },
                        "required": ["domain", "service", "entity_id"],
                        "additionalProperties": False,
                    },
                ),
                handler=self._call_service,
            ),
        ]

    def _entity_allowed(self, entity_id: str) -> bool:
        for pattern in self._entity_allowlist:
            if pattern.endswith("*"):
                if entity_id.startswith(pattern[:-1]):
                    return True
            elif entity_id == pattern:
                return True
        return False

    def _service_allowed(self, domain: str, service: str) -> bool:
        full = f"{domain}.{service}"
        return full in self._service_allowlist or f"{domain}.*" in self._service_allowlist

    async def _get_state(self, args: dict[str, Any]) -> str:
        entity_id = str(args["entity_id"]).strip()
        if not self._entity_allowed(entity_id):
            raise ValueError("Entity is not allowlisted")
        data = await self._request("GET", f"/api/states/{entity_id}")
        return json.dumps(self._minimize_state(data))

    async def _list_states(self, args: dict[str, Any]) -> str:
        limit = int(args.get("limit", 50))
        data = await self._request("GET", "/api/states")
        if not isinstance(data, list):
            raise ValueError("Unexpected Home Assistant response")
        states = []
        for item in data:
            if not isinstance(item, dict):
                continue
            entity_id = str(item.get("entity_id", ""))
            if not self._entity_allowed(entity_id):
                continue
            states.append(self._minimize_state(item))
            if len(states) >= limit:
                break
        return json.dumps({"states": states})

    async def _call_service(self, args: dict[str, Any]) -> str:
        domain = str(args["domain"]).strip()
        service = str(args["service"]).strip()
        entity_id = str(args["entity_id"]).strip()
        if not self._entity_allowed(entity_id):
            raise ValueError("Entity is not allowlisted")
        if not self._service_allowed(domain, service):
            raise ValueError("Service is not allowlisted")
        await self._request(
            "POST",
            f"/api/services/{domain}/{service}",
            json_body={"entity_id": entity_id},
        )
        return json.dumps(
            {
                "domain": domain,
                "service": service,
                "entity_id": entity_id,
                "status": "accepted",
            }
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        assert self._client is not None
        url = f"{self._base_url}{path}"
        await self._validate_base_url(url)
        response = await self._client.request(method, url, json=json_body)
        response.raise_for_status()
        content = response.content
        if len(content) > self._max_response_bytes:
            raise ValueError("Home Assistant response exceeds size limit")
        if not content:
            return {}
        return response.json()

    async def _validate_base_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise UnsafeOutboundURLError("Home Assistant URL must be HTTP(S)")
        if parsed.username or parsed.password:
            raise UnsafeOutboundURLError("Credentials are not allowed in Home Assistant URLs")
        if parsed.scheme == "http" and not self._allow_insecure_http:
            raise UnsafeOutboundURLError("Insecure HTTP is disabled for Hephaestus")
        hostname = parsed.hostname.lower().rstrip(".")
        try:
            addresses = [ipaddress.ip_address(hostname)]
        except ValueError:
            loop = asyncio.get_running_loop()
            try:
                records = await loop.getaddrinfo(
                    hostname,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            except socket.gaierror as exc:
                raise UnsafeOutboundURLError("Home Assistant host could not be resolved") from exc
            addresses = [ipaddress.ip_address(record[4][0]) for record in records]
        if not addresses or any(
            address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or (address.is_reserved and not address.is_loopback and not address.is_private)
            for address in addresses
        ):
            raise UnsafeOutboundURLError("Forbidden Home Assistant destination")
        if any(str(address) == "169.254.169.254" for address in addresses):
            raise UnsafeOutboundURLError("Forbidden Home Assistant destination")
        if not self._allow_private_hosts and any(
            address.is_private or address.is_loopback for address in addresses
        ):
            raise UnsafeOutboundURLError("Private Home Assistant destinations are blocked")

    @staticmethod
    def _minimize_state(data: dict[str, Any]) -> dict[str, Any]:
        attributes = data.get("attributes")
        friendly = None
        if isinstance(attributes, dict):
            friendly = attributes.get("friendly_name")
            if isinstance(friendly, str):
                friendly = friendly[:200]
            else:
                friendly = None
        return {
            "entity_id": str(data.get("entity_id", ""))[:200],
            "state": str(data.get("state", ""))[:200],
            "friendly_name": friendly,
            "last_changed": str(data.get("last_changed", ""))[:64] or None,
        }
