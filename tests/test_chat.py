def test_chat_success(client_with_mock_llm, auth_headers):
    response = client_with_mock_llm.post(
        "/chat",
        json={"message": "What's the weather in Austin?"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"]
    assert "Austin" in data["message"]


def test_chat_rejects_message_too_long(client, auth_headers):
    long_message = "x" * 5000
    response = client.post(
        "/chat",
        json={"message": long_message},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "too long" in response.json()["detail"].lower()


def test_chat_rejects_invalid_session_id(client_with_mock_llm, auth_headers):
    response = client_with_mock_llm.post(
        "/chat",
        json={"message": "Hi", "session_id": "not-a-uuid"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_chat_stream_success(client_with_mock_llm, auth_headers):
    response = client_with_mock_llm.post(
        "/chat/stream",
        json={"message": "Hello Hestia"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.text
    assert '"type": "session"' in body
    assert '"type": "token"' in body
    assert '"type": "done"' in body
    assert "Hestia" in body or "Sunny" in body


def test_chat_stream_requires_auth(client):
    response = client.post("/chat/stream", json={"message": "Hello"})
    assert response.status_code == 401


def test_chat_preserves_session(client_with_mock_llm, auth_headers):
    first = client_with_mock_llm.post(
        "/chat",
        json={"message": "First message"},
        headers=auth_headers,
    )
    session_id = first.json()["session_id"]

    second = client_with_mock_llm.post(
        "/chat",
        json={"message": "Second message", "session_id": session_id},
        headers=auth_headers,
    )
    assert second.json()["session_id"] == session_id
    assert client_with_mock_llm.app.state.orchestrator._llm.chat.call_count == 2
