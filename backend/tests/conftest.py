"""Pytest fixtures for automated tests."""

import pytest
from backend.app import create_app
from backend.config import TestConfig
from backend.models.base import (
    Base,
    db_session,
    remove_session,
    create_all_tables,
    drop_all_tables,
)
from backend.models.user import User, UserRole
from backend.models.inventory import InventoryItem, InventoryTransaction, ItemType, TransactionType
from backend.services.auth_service import clear_all_failed_logins


@pytest.fixture(scope="session")
def app():
    """Session-wide test application."""
    test_app = create_app(TestConfig)
    return test_app


@pytest.fixture(autouse=True)
def clean_db(app):
    """Ensures each test runs with a completely fresh, isolated database and reset rate limits."""
    clear_all_failed_logins()
    with app.app_context():
        drop_all_tables()
        create_all_tables()
        yield db_session
        db_session.rollback()
        remove_session()


@pytest.fixture
def client(app):
    """Test HTTP client."""
    return app.test_client()


@pytest.fixture
def admin_user(app):
    """Creates a sample Administrator user."""
    with app.app_context():
        user = User(
            username="admin_test",
            email="admin@test.com",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("AdminSecurePass123!")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user


@pytest.fixture
def organizer_user(app):
    """Creates a sample Event Organizer user."""
    with app.app_context():
        user = User(
            username="organizer_test",
            email="organizer@test.com",
            role=UserRole.ORGANIZER,
            is_active=True,
        )
        user.set_password("OrganizerPass123!")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user


@pytest.fixture
def other_organizer_user(app):
    """Creates a second Event Organizer user to test data isolation."""
    with app.app_context():
        user = User(
            username="other_organizer",
            email="other@test.com",
            role=UserRole.ORGANIZER,
            is_active=True,
        )
        user.set_password("OtherPass123!")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user


@pytest.fixture
def admin_client(app, admin_user):
    """Client authenticated as Administrator."""
    c = app.test_client()
    resp = c.post(
        "/api/auth/login",
        json={"username": admin_user.username, "password": "AdminSecurePass123!"},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.get_json()}"
    return c


@pytest.fixture
def organizer_client(app, organizer_user):
    """Client authenticated as Event Organizer."""
    c = app.test_client()
    resp = c.post(
        "/api/auth/login",
        json={"username": organizer_user.username, "password": "OrganizerPass123!"},
    )
    assert resp.status_code == 200, f"Organizer login failed: {resp.get_json()}"
    return c


@pytest.fixture
def sample_chair(app, admin_user):
    """Creates a sample inventory item."""
    with app.app_context():
        item = InventoryItem(
            name="Banquet Chair",
            category="Chairs",
            description="Padded banquet chair",
            item_type=ItemType.RETURNABLE,
            total_stock=100,
            unavailable_stock=0,
            minimum_threshold=10,
            unit="pieces",
            purchase_cost=25.0,
            is_active=True,
        )
        db_session.add(item)
        db_session.flush()

        tx = InventoryTransaction(
            item_id=item.id,
            user_id=admin_user.id,
            change_amount=100,
            previous_total_stock=0,
            new_total_stock=100,
            transaction_type=TransactionType.INITIAL,
            reason="Initial stock",
        )
        db_session.add(tx)
        db_session.commit()
        db_session.refresh(item)
        return item
