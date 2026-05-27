from __future__ import annotations

from datetime import datetime, timedelta

import jwt


def _make_auth_headers(app_module, *, user_id: str, business_id: str) -> dict[str, str]:
    token = jwt.encode(
        {
            "user_id": user_id,
            "business_id": business_id,
            "exp": datetime.utcnow() + timedelta(hours=1),
        },
        app_module.app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_chat_conversations_require_authentication(client):
    response = client.get("/api/chat/conversations")

    assert response.status_code == 401
    assert response.get_json()["message"] == "Authorization header is required"


def test_chat_conversation_messages_round_trip(client, auth_headers):
    response = client.post(
        "/api/chat/conversations/conv-1/messages",
        headers=auth_headers,
        json={
            "title": "Revenue review",
            "message": {
                "role": "user",
                "content": "What was revenue last month?",
                "timestamp": 1710000000000,
            },
        },
    )

    assert response.status_code == 201

    response = client.post(
        "/api/chat/conversations/conv-1/messages",
        headers=auth_headers,
        json={
            "title": "Revenue review",
            "message": {
                "role": "assistant",
                "content": "Revenue was up 12%.",
                "intent": "metrics_request",
                "timestamp": 1710000000100,
            },
        },
    )

    assert response.status_code == 201

    response = client.get("/api/chat/conversations", headers=auth_headers)

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["conversations"] == [
        {
            "id": "conv-1",
            "title": "Revenue review",
            "createdAt": 1710000000000,
            "updatedAt": 1710000000100,
            "messages": [
                {
                    "role": "user",
                    "content": "What was revenue last month?",
                    "intent": None,
                    "timestamp": 1710000000000,
                },
                {
                    "role": "assistant",
                    "content": "Revenue was up 12%.",
                    "intent": "metrics_request",
                    "timestamp": 1710000000100,
                },
            ],
        }
    ]


def test_chat_conversations_are_scoped_to_authenticated_owner(client, app_module, auth_headers):
    response = client.post(
        "/api/chat/conversations/conv-1/messages",
        headers=auth_headers,
        json={
            "title": "Private chat",
            "message": {
                "role": "user",
                "content": "Show my private numbers",
                "timestamp": 1710000000000,
            },
        },
    )

    assert response.status_code == 201

    other_headers = _make_auth_headers(
        app_module,
        user_id="user-2",
        business_id="business-2",
    )

    response = client.get("/api/chat/conversations", headers=other_headers)

    assert response.status_code == 200
    assert response.get_json() == {"conversations": []}


def test_put_chat_conversation_dedupes_existing_messages(client, auth_headers):
    payload = {
        "title": "Imported chat",
        "createdAt": 1710000000000,
        "updatedAt": 1710000000300,
        "messages": [
            {
                "role": "user",
                "content": "What changed this week?",
                "timestamp": 1710000000000,
            },
            {
                "role": "assistant",
                "content": "Revenue improved while expenses stayed flat.",
                "intent": "database_request",
                "timestamp": 1710000000300,
            },
        ],
    }

    response = client.put(
        "/api/chat/conversations/import-1",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 200

    response = client.put(
        "/api/chat/conversations/import-1",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 200

    response = client.get("/api/chat/conversations/import-1", headers=auth_headers)

    conversation = response.get_json()["conversation"]
    assert response.status_code == 200
    assert conversation["messages"] == [
        {
            "role": "user",
            "content": "What changed this week?",
            "intent": None,
            "timestamp": 1710000000000,
        },
        {
            "role": "assistant",
            "content": "Revenue improved while expenses stayed flat.",
            "intent": "database_request",
            "timestamp": 1710000000300,
        },
    ]
    assert conversation["updatedAt"] == 1710000000300


def test_delete_chat_conversation_removes_it_from_history(client, auth_headers):
    response = client.put(
        "/api/chat/conversations/conv-delete",
        headers=auth_headers,
        json={
            "title": "Delete me",
            "createdAt": 1710000000000,
            "updatedAt": 1710000000000,
            "messages": [
                {
                    "role": "user",
                    "content": "Ephemeral note",
                    "timestamp": 1710000000000,
                }
            ],
        },
    )

    assert response.status_code == 200

    response = client.delete("/api/chat/conversations/conv-delete", headers=auth_headers)

    assert response.status_code == 204

    response = client.get("/api/chat/conversations", headers=auth_headers)

    payload = response.get_json()
    assert response.status_code == 200
    assert all(conversation["id"] != "conv-delete" for conversation in payload["conversations"])
