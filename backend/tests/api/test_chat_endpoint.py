"""`POST /chat` — happy path for the keyword-routed intents plus the
direct-completion fallback, all under `DEVBRAIN_LLM_MODE=stub`."""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import USER_TOKEN, VIEWER_TOKEN


def test_chat_falls_back_to_direct_completion_for_an_unmatched_message(client: TestClient) -> None:
    response = client.post(
        "/chat",
        json={"message": "hello there, how are you?"},
        headers={"Authorization": f"Bearer {VIEWER_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "none"
    assert body["orchestrator"] is None
    assert body["reply"]  # stub LLM still returns non-empty text


def test_chat_routes_daily_briefing_intent(client: TestClient) -> None:
    response = client.post(
        "/chat",
        json={"message": "give me the daily briefing"},
        headers={"Authorization": f"Bearer {VIEWER_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "daily_briefing"
    assert body["orchestrator"] == "daily_briefing"
    assert "calendar_event_count" in body["data"]


def test_chat_safe_write_intent_never_executes_a_write(client: TestClient) -> None:
    response = client.post(
        "/chat",
        json={"message": "please create a task for me"},
        headers={"Authorization": f"Bearer {VIEWER_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "safe_write"
    assert body["orchestrator"] is None
    assert "approve" in body["reply"].lower()


def test_chat_weekly_digest_requires_user_role(client: TestClient) -> None:
    # weekly_digest writes a note - a viewer (below Role.USER) must be
    # refused even though /chat's own baseline minimum is Role.VIEWER.
    response = client.post(
        "/chat",
        json={"message": "weekly digest please"},
        headers={"Authorization": f"Bearer {VIEWER_TOKEN}"},
    )
    assert response.status_code == 403


def test_chat_weekly_digest_intent_creates_a_digest_note(client: TestClient) -> None:
    response = client.post(
        "/chat",
        json={"message": "weekly digest please"},
        headers={"Authorization": f"Bearer {USER_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "weekly_digest"
    assert body["orchestrator"] == "weekly_digest"
    assert "digest_note" in body["data"]
