import httpx
import pytest

from hestia.security.http import (
    SecureHTTPClient,
    UnsafeOutboundURLError,
    validate_outbound_url,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://calendar.example/events.ics",
        "https://127.0.0.1/events.ics",
        "https://localhost/events.ics",
        "https://user:password@calendar.example/events.ics",
    ],
)
async def test_outbound_url_policy_rejects_unsafe_destinations(url):
    with pytest.raises(UnsafeOutboundURLError):
        await validate_outbound_url(url)


@pytest.mark.asyncio
async def test_explicit_private_host_override_is_required():
    address = await validate_outbound_url(
        "https://127.0.0.1/events.ics",
        allow_private_hosts=True,
    )
    assert address == "127.0.0.1"


@pytest.mark.asyncio
async def test_private_override_never_allows_link_local_metadata():
    with pytest.raises(UnsafeOutboundURLError):
        await validate_outbound_url(
            "https://169.254.169.254/latest/meta-data",
            allow_private_hosts=True,
        )


@pytest.mark.asyncio
async def test_secure_client_enforces_response_size_limit():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "127.0.0.1"
        assert request.headers["host"] == "localhost"
        return httpx.Response(200, content=b"x" * 20)

    raw_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = SecureHTTPClient(
        timeout_seconds=1,
        max_response_bytes=10,
        allow_private_hosts=True,
        client=raw_client,
    )
    with pytest.raises(ValueError, match="size limit"):
        await client.get_bytes("https://localhost/calendar.ics")
    await raw_client.aclose()


@pytest.mark.asyncio
async def test_secure_client_rejects_unexpected_content_type():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html>not a calendar</html>",
            headers={"content-type": "text/html"},
        )

    raw_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = SecureHTTPClient(
        timeout_seconds=1,
        max_response_bytes=100,
        allow_private_hosts=True,
        client=raw_client,
    )
    with pytest.raises(ValueError, match="content type"):
        await client.get_bytes(
            "https://localhost/calendar.ics",
            allowed_content_types={"text/calendar"},
        )
    await raw_client.aclose()
