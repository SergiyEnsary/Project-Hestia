from unittest.mock import AsyncMock, patch

import httpx


def test_health_includes_ollama_status(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "hestia"
    assert "ollama" in data
    assert data["ollama"] in ("ok", "unreachable", "error", "unknown")
    assert "model" not in data
    assert "ollama_url" not in data
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-request-id"]


def test_health_ollama_unreachable(client):
    with patch("hestia.api.routes.health.httpx.AsyncClient") as mock_client_cls:
        instance = mock_client_cls.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        response = client.get("/health")
    assert response.json()["ollama"] == "unreachable"
