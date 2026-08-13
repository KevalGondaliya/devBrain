"""`POST /auth/login` + the shared `require_role` dependency's auth
boundary (401/403), exercised through every other router too."""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import ADMIN_TOKEN, VIEWER_TOKEN


def test_login_accepts_a_known_token_and_resolves_its_role(client: TestClient) -> None:
    response = client.post("/auth/login", json={"token": ADMIN_TOKEN})
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin"
    assert body["actor"].startswith("token:")
    assert ADMIN_TOKEN not in body["actor"]  # never echoes the raw token


def test_login_rejects_an_unknown_token(client: TestClient) -> None:
    response = client.post("/auth/login", json={"token": "not-a-real-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_missing_authorization_header_is_401(client: TestClient) -> None:
    response = client.get("/tools")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_insufficient_role_is_403(client: TestClient) -> None:
    # /activity requires Role.USER; a viewer token is under that bar.
    response = client.get("/activity", headers={"Authorization": f"Bearer {VIEWER_TOKEN}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
