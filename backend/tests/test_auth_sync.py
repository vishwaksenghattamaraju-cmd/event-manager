"""
Tests for Authentication & UI Synchronization (Register and Sign In sections).
Ensures registration and sign in are fully synchronized across UI, client state, and backend.
"""

from pathlib import Path
import pytest
from backend.models.user import User, UserRole
from backend.services.auth_service import register_user, authenticate_user

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def test_auth_sync_user_registration_and_login_case_and_spacing(clean_db):
    """Verify registration and login work identically with whitespace and case variations."""
    username = "  vishwaksen   ghattamaraju  "
    email = " VishwakSen.G@Example.COM "
    password = "MySecurePassword123!"

    user, error = register_user(
        clean_db, username, email, password, role=UserRole.ORGANIZER
    )
    assert error is None
    assert user is not None
    assert user.username == "vishwaksen ghattamaraju"
    assert user.email == "vishwaksen.g@example.com"
    assert user.role == UserRole.ORGANIZER

    # 1. Login by normalized username
    logged_in_user, err = authenticate_user(
        clean_db, "vishwaksen ghattamaraju", password
    )
    assert err is None
    assert logged_in_user.id == user.id

    # 2. Login by un-trimmed / uppercase username
    logged_in_user2, err2 = authenticate_user(
        clean_db, "  VISHWAKSEN GHATTAMARAJU  ", password
    )
    assert err2 is None
    assert logged_in_user2.id == user.id

    # 3. Login by email
    logged_in_user3, err3 = authenticate_user(
        clean_db, "vishwaksen.g@example.com", password
    )
    assert err3 is None
    assert logged_in_user3.id == user.id

    # 4. Login by uppercase email
    logged_in_user4, err4 = authenticate_user(
        clean_db, "VISHWAKSEN.G@EXAMPLE.COM", password
    )
    assert err4 is None
    assert logged_in_user4.id == user.id


def test_login_and_public_html_parity_and_sync_elements():
    """Verify 100% parity and presence of synchronized UI elements across login HTML files."""
    frontend_login = (ROOT_DIR / "frontend" / "pages" / "login.html").read_text(encoding="utf-8")
    public_login = (ROOT_DIR / "public" / "login.html").read_text(encoding="utf-8")
    public_index = (ROOT_DIR / "public" / "index.html").read_text(encoding="utf-8")

    # Parity check
    assert frontend_login == public_login, "frontend/pages/login.html and public/login.html must be identical"
    assert public_login == public_index, "public/login.html and public/index.html must be identical"

    # Required sync elements
    assert 'id="auth-title"' in frontend_login
    assert 'id="auth-subtitle"' in frontend_login
    assert 'id="tab-login"' in frontend_login
    assert 'id="tab-register"' in frontend_login
    assert 'id="link-goto-register"' in frontend_login
    assert 'id="link-goto-login"' in frontend_login
    assert 'id="btn-fill-registered"' in frontend_login
    assert 'id="btn-fill-admin"' in frontend_login
    assert 'id="btn-fill-organizer"' in frontend_login


def test_login_js_parity_and_sync_logic():
    """Verify parity and presence of synchronization logic in login.js."""
    frontend_js = (ROOT_DIR / "frontend" / "js" / "login.js").read_text(encoding="utf-8")
    public_js = (ROOT_DIR / "public" / "js" / "login.js").read_text(encoding="utf-8")

    assert frontend_js == public_js, "frontend/js/login.js and public/js/login.js must be identical"

    # Title & Subtitle synchronization
    assert "Create Account" in frontend_js
    assert "Sign up to get started with The Matrix" in frontend_js
    assert "Sign in to continue to The Matrix" in frontend_js

    # Input value handoff synchronization between tabs
    assert "inputRegEmail.value = loginVal" in frontend_js or "inputRegUser.value = loginVal" in frontend_js
    assert "inputLoginUser.value = regUser" in frontend_js or "inputLoginUser.value = regEmail" in frontend_js

    # Contextual links
    assert "link-goto-register" in frontend_js
    assert "link-goto-login" in frontend_js

    # Hash sync
    assert "hashchange" in frontend_js
    assert "setupRegisteredUserChip" in frontend_js


def test_api_js_parity_and_serverless_vault_sync():
    """Verify parity and serverless resilience sync in api.js."""
    frontend_api = (ROOT_DIR / "frontend" / "js" / "api.js").read_text(encoding="utf-8")
    public_api = (ROOT_DIR / "public" / "js" / "api.js").read_text(encoding="utf-8")

    assert frontend_api == public_api, "frontend/js/api.js and public/js/api.js must be identical"

    # Vault sync keywords
    assert "matrix_registered_accounts" in frontend_api
    assert "matrix_last_username" in frontend_api
    assert "Serverless cold start detected" in frontend_api
