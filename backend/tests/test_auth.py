"""Tests for authentication and role-based access control (RBAC)."""

import pytest
from backend.services.auth_service import clear_failed_logins


def test_valid_login_works(client, organizer_user):
    """Test 1: Valid login succeeds and sets up session."""
    response = client.post(
        "/api/auth/login",
        json={"username": organizer_user.username, "password": "OrganizerPass123!"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "user" in data
    assert data["user"]["username"] == organizer_user.username
    assert data["user"]["role"] == "organizer"
    # Ensure password hash is never leaked
    assert "password_hash" not in data["user"]
    assert "csrf_token" in data

    # Verify session persists by calling /api/auth/me
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    me_data = me_resp.get_json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["id"] == organizer_user.id


def test_wrong_password_is_rejected(client, organizer_user):
    """Test 2: Incorrect password returns 401 Unauthorized."""
    clear_failed_logins(organizer_user.username)
    response = client.post(
        "/api/auth/login",
        json={"username": organizer_user.username, "password": "WrongPassword999!"},
    )
    assert response.status_code == 401
    data = response.get_json()
    assert "error" in data
    assert "Invalid username or password" in data["error"]


def test_organizer_cannot_access_admin_endpoints(organizer_client):
    """Test 3: Organizer attempting to perform admin action receives 403 Forbidden."""
    # Attempt to create an inventory item (Admin only)
    response = organizer_client.post(
        "/api/inventory",
        json={
            "name": "Luxury Tent",
            "category": "Decor",
            "total_stock": 5,
        },
    )
    assert response.status_code == 403
    data = response.get_json()
    assert "Forbidden" in data["error"]


def test_unauthenticated_access_rejected(client):
    """Ensure accessing protected routes without logging in returns 401."""
    response = client.get("/api/inventory")
    assert response.status_code == 401
    assert "Authentication required" in response.get_json()["error"]


def test_logout_clears_session(organizer_client):
    """Ensure logging out terminates user session."""
    logout_resp = organizer_client.post("/api/auth/logout")
    assert logout_resp.status_code == 200

    me_resp = organizer_client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.get_json()["authenticated"] is False


def test_rate_limiting_triggers_after_repeated_failures(client, organizer_user):
    """Ensure excessive failed login attempts result in 429 Too Many Requests."""
    clear_failed_logins(organizer_user.username)
    for _ in range(5):
        resp = client.post(
            "/api/auth/login",
            json={"username": organizer_user.username, "password": "BadPassword!"},
        )
        assert resp.status_code in (401, 429)

    # 6th attempt should be blocked by rate limit
    blocked_resp = client.post(
        "/api/auth/login",
        json={"username": organizer_user.username, "password": "BadPassword!"},
    )
    assert blocked_resp.status_code == 429
    assert "Too many failed login attempts" in blocked_resp.get_json()["error"]
    clear_failed_logins(organizer_user.username)
