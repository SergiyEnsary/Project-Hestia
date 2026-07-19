from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


class UnsafeOutboundURLError(ValueError):
    pass


async def validate_outbound_url(
    url: str,
    *,
    allowed_hosts: set[str] | None = None,
    allow_private_hosts: bool = False,
) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise UnsafeOutboundURLError("Outbound URLs must use HTTPS")
    if parsed.username or parsed.password:
        raise UnsafeOutboundURLError("Credentials are not allowed in outbound URLs")

    hostname = parsed.hostname.lower().rstrip(".")
    if allowed_hosts is not None and hostname not in allowed_hosts:
        raise UnsafeOutboundURLError("Outbound destination is not allowlisted")
    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            records = await loop.getaddrinfo(
                hostname,
                parsed.port or 443,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise UnsafeOutboundURLError("Outbound destination could not be resolved") from exc
        addresses = [ipaddress.ip_address(record[4][0]) for record in records]

    if not addresses or any(
        address.is_link_local
        or address.is_multicast
        or (address.is_reserved and not address.is_loopback)
        or address.is_unspecified
        for address in addresses
    ):
        raise UnsafeOutboundURLError("Forbidden outbound destination")
    if not allow_private_hosts and any(
        address.is_private or address.is_loopback for address in addresses
    ):
        raise UnsafeOutboundURLError("Private outbound destinations are blocked")
    return str(
        sorted(
            set(addresses),
            key=lambda address: (address.version, int(address)),
        )[0]
    )


class SecureHTTPClient:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
        allowed_hosts: set[str] | None = None,
        allow_private_hosts: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._max_response_bytes = max_response_bytes
        self._allowed_hosts = allowed_hosts
        self._allow_private_hosts = allow_private_hosts
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )

    async def get_bytes(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        allowed_content_types: set[str] | None = None,
    ) -> bytes:
        resolved_address = await validate_outbound_url(
            url,
            allowed_hosts=self._allowed_hosts,
            allow_private_hosts=self._allow_private_hosts,
        )
        parsed = urlsplit(url)
        address_literal = f"[{resolved_address}]" if ":" in resolved_address else resolved_address
        pinned_netloc = f"{address_literal}:{parsed.port}" if parsed.port else address_literal
        pinned_url = urlunsplit(
            (
                parsed.scheme,
                pinned_netloc,
                parsed.path,
                parsed.query,
                "",
            )
        )
        async with self._client.stream(
            "GET",
            pinned_url,
            params=params,
            headers={"Host": parsed.netloc},
            extensions={"sni_hostname": parsed.hostname},
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").partition(";")[0]
            if (
                allowed_content_types is not None
                and content_type
                and content_type.lower() not in allowed_content_types
            ):
                raise ValueError("Upstream response has an unsupported content type")
            declared_size = response.headers.get("content-length")
            if declared_size:
                try:
                    content_length = int(declared_size)
                except ValueError as exc:
                    raise ValueError("Upstream response has an invalid size") from exc
                if content_length > self._max_response_bytes:
                    raise ValueError("Upstream response exceeds the configured size limit")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self._max_response_bytes:
                    raise ValueError("Upstream response exceeds the configured size limit")
                chunks.append(chunk)
            return b"".join(chunks)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
