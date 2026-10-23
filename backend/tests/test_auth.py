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


def test_login_with_username_or_email_payload_key(client, organizer_user):
    """Test login succeeds when using the frontend 'username_or_email' payload key."""
    # Test using username in username_or_email
    res1 = client.post(
        "/api/auth/login",
        json={"username_or_email": organizer_user.username, "password": "OrganizerPass123!"},
    )
    assert res1.status_code == 200
    assert res1.get_json()["user"]["username"] == organizer_user.username

    # Test using email in username_or_email
    res2 = client.post(
        "/api/auth/login",
        json={"username_or_email": organizer_user.email, "password": "OrganizerPass123!"},
    )
    assert res2.status_code == 200
    assert res2.get_json()["user"]["email"] == organizer_user.email


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


def test_toggle_role_from_organizer_to_admin_and_back(client, organizer_user):
    """Ensure switching from Organizer to Admin persists across requests and updates role."""
    # 1. Log in as organizer
    login_resp = client.post(
        "/api/auth/login",
        json={"username": organizer_user.username, "password": "OrganizerPass123!"},
    )
    assert login_resp.status_code == 200
    csrf = login_resp.get_json()["csrf_token"]

    # 2. Toggle role to Admin
    toggle_resp = client.post(
        "/api/auth/toggle-role",
        headers={"X-CSRF-Token": csrf}
    )
    assert toggle_resp.status_code == 200
    data = toggle_resp.get_json()
    assert data["role"] == "admin"
    assert data["is_admin"] is True
    assert data["user"]["role"] == "admin"
    assert data["user"]["is_admin"] is True

    # 3. Verify /me immediately reflects Admin role and stays authenticated
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    me_data = me_resp.get_json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["role"] == "admin"
    assert me_data["user"]["is_admin"] is True

    # 4. Toggle back to Organizer
    toggle_back_resp = client.post(
        "/api/auth/toggle-role",
        headers={"X-CSRF-Token": csrf}
    )
    assert toggle_back_resp.status_code == 200
    data_back = toggle_back_resp.get_json()
    assert data_back["role"] == "organizer"
    assert data_back["is_admin"] is False

    # 5. Verify /me reflects Organizer role
    me_resp2 = client.get("/api/auth/me")
    assert me_resp2.status_code == 200
    assert me_resp2.get_json()["user"]["role"] == "organizer"
    assert me_resp2.get_json()["user"]["is_admin"] is False


def test_session_recovery_by_username_if_user_id_mismatched(client, organizer_user):
    """Ensure session recovers authenticated user via username if user_id points to stale ID."""
    with client.session_transaction() as sess:
        sess["user_id"] = 999999  # stale or non-existent ID
        sess["username"] = organizer_user.username
        sess["role"] = "organizer"

    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    me_data = me_resp.get_json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["username"] == organizer_user.username
    assert me_data["user"]["id"] == organizer_user.id


def test_register_admin_user(client):
    """Ensure user can register directly with the admin role."""
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "new_admin_user",
            "email": "newadmin@eventinventory.com",
            "password": "AdminPassword123!",
            "role": "admin",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["user"]["username"] == "new_admin_user"
    assert data["user"]["role"] == "admin"

    # Verify session is established with admin privileges
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    me_data = me_resp.get_json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["role"] == "admin"
    assert me_data["user"]["is_admin"] is True


def test_update_user_profile(organizer_client, organizer_user):
    """Ensure authenticated user can update profile email."""
    new_email = "updated_organizer@example.com"
    resp = organizer_client.put(
        "/api/auth/profile",
        json={"email": new_email},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user"]["email"] == new_email

    # Verify /me reflects updated email
    me_resp = organizer_client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.get_json()["user"]["email"] == new_email


def test_delete_user_account(client):
    """Ensure user can delete their account and subsequent access is unauthenticated."""
    # Register a temporary user
    reg_resp = client.post(
        "/api/auth/register",
        json={
            "username": "delete_me_user",
            "email": "deleteme@example.com",
            "password": "Password123!",
            "role": "organizer",
        },
    )
    assert reg_resp.status_code == 201

    # Verify user is logged in
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.get_json()["authenticated"] is True

    # Delete the account
    del_resp = client.delete("/api/auth/account")
    assert del_resp.status_code == 200
    assert del_resp.get_json()["deleted"] is True

    # Verify session is now terminated
    me_after = client.get("/api/auth/me")
    assert me_after.status_code == 200
    assert me_after.get_json()["authenticated"] is False


def test_delete_account_unauthenticated(client):
    """Ensure unauthenticated request to delete account is rejected with 401."""
    resp = client.delete("/api/auth/account")
    assert resp.status_code == 401
    assert "Authentication required" in resp.get_json()["error"]


def test_cannot_delete_primary_admin(admin_client):
    """Ensure the system prevents deleting the lone primary administrator account."""
    resp = admin_client.delete("/api/auth/account")
    assert resp.status_code == 400
    assert "primary administrator account cannot be deleted" in resp.get_json()["error"]



