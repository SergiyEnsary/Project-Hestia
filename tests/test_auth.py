def test_health_unauthenticated(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_requires_auth(client):
    response = client.post("/chat", json={"message": "Hello"})
    assert response.status_code == 401


def test_chat_rejects_invalid_token(client):
    response = client.post(
        "/chat",
        json={"message": "Hello"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_chat_rejects_empty_message(client, auth_headers):
    response = client.post("/chat", json={"message": "   "}, headers=auth_headers)
    assert response.status_code == 422


def test_chat_valid_token_accepted(client_with_mock_llm, auth_headers):
    response = client_with_mock_llm.post(
        "/chat",
        json={"message": "Hello"},
        headers=auth_headers,
    )
    assert response.status_code == 200
