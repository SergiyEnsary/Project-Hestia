from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_TOKEN = "test-token-for-unit-tests"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    shutil.copy(PROJECT_ROOT / "config.yaml.example", tmp_path / "config.yaml")
    (tmp_path / ".env").write_text(f"HESTIA_API_TOKEN={TEST_TOKEN}\n", encoding="utf-8")

    import os

    os.environ["HESTIA_CONFIG"] = str(tmp_path / "config.yaml")

    from hestia.api.app import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def client_with_mock_llm(client: TestClient) -> TestClient:
    from unittest.mock import AsyncMock

    from hestia.core.tools.models import ChatMessage

    client.app.state.orchestrator._llm.chat = AsyncMock(
        return_value=ChatMessage(role="assistant", content="Sunny and 85°F in Austin.")
    )
    return client
