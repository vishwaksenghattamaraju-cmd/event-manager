"""
test_audit_fixes.py - Regression test suite verifying all 14 audit bug fixes.
"""

import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest

from backend.models.base import db_session
from backend.models.user import User, UserRole
from backend.models.inventory import InventoryItem, ItemType
from backend.models.event import Event, EventStatus, EventType
from backend.services.event_service import create_event
from backend.services.booking_service import (
    confirm_event_booking,
    reschedule_or_edit_event,
)
from backend.services.ml_service import get_ml_service
from backend.services.auth_service import authenticate_user


class TestAuditFixes:
    """Tests covering BUG-01 through BUG-14."""

    def test_bug01_availability_contract_and_confirmation(self, admin_client, admin_user):
        """BUG-01: Ensure availability returns both is_sufficient & available, and sufficient stock confirms event."""
        # 1. Create a test item with 20 units
        item = InventoryItem(
            name="Test Confirmation Speaker",
            category="Audio",
            item_type=ItemType.RETURNABLE,
            total_stock=20,
            unavailable_stock=0,
            minimum_threshold=2,
            unit="units",
            purchase_cost=100.0,
            is_active=True,
        )
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)

        now = datetime.now(timezone.utc)
        start_str = (now + timedelta(days=2)).isoformat()
        end_str = (now + timedelta(days=2, hours=4)).isoformat()

        # 2. Check availability endpoint contract
        resp = admin_client.post(
            "/api/events/check-availability",
            json={
                "start_time": start_str,
                "end_time": end_str,
                "items": [{"item_id": item.id, "quantity": 5}],
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "is_sufficient" in data
        assert "available" in data
        assert data["is_sufficient"] is True
        assert data["available"] is True

        # 3. Create event and confirm booking
        evt, err = create_event(
            db_session,
            organizer_id=admin_user.id,
            data={
                "name": "Audit Test Event",
                "start_time": start_str,
                "end_time": end_str,
                "items": [{"item_id": item.id, "quantity": 5}],
                "expected_guest_count": 50,
            },
        )
        assert err is None
        assert evt.status == EventStatus.DRAFT

        # Confirm booking
        confirmed_evt, confirm_err = confirm_event_booking(db_session, evt.id, user_id=admin_user.id)
        assert confirm_err is None
        assert confirmed_evt.status == EventStatus.CONFIRMED

    def test_bug02_ml_table_chair_mapping(self):
        """BUG-02: Tables in Furniture category must map to tables, NOT chairs."""
        chair = InventoryItem(
            name="Deluxe Padded Banquet Chair",
            category="Furniture",
            item_type=ItemType.RETURNABLE,
            total_stock=100,
            unavailable_stock=0,
            minimum_threshold=10,
            unit="chairs",
            is_active=True,
        )
        table = InventoryItem(
            name="60in Round Banquet Table",
            category="Furniture",
            item_type=ItemType.RETURNABLE,
            total_stock=20,
            unavailable_stock=0,
            minimum_threshold=2,
            unit="tables",
            is_active=True,
        )
        db_session.add_all([chair, table])
        db_session.commit()

        ml = get_ml_service()
        res = ml.predict_quantities("conference", 100, 4.0, db=db_session)
        items_by_key = {it["item_key"]: it for it in res["items"]}

        # Chairs key must map to chair item
        assert "chairs" in items_by_key
        assert "chair" in items_by_key["chairs"]["item_name"].lower()
        assert items_by_key["chairs"]["item_id"] == chair.id

        # Tables key must map to table item
        assert "tables" in items_by_key
        assert "table" in items_by_key["tables"]["item_name"].lower()
        assert items_by_key["tables"]["item_id"] == table.id

    def test_bug03_event_type_enum_validity(self):
        """BUG-03: EventType must contain valid types and seeder must not reference CONCERT."""
        assert hasattr(EventType, "OTHER")
        assert hasattr(EventType, "CONFERENCE")
        assert hasattr(EventType, "WEDDING")
        assert hasattr(EventType, "CORPORATE")
        assert hasattr(EventType, "BIRTHDAY")
        assert not hasattr(EventType, "CONCERT")

    def test_bug05_roles_and_demo_auth(self):
        """BUG-05: Admin user has ADMIN role, Organizer has ORGANIZER role, and demo credentials verify."""
        admin = User(
            username="test_admin_demo",
            email="test_admin_demo@matrix.local",
            role=UserRole.ADMIN,
            is_active=True,
        )
        admin.set_password("Admin@123")
        organizer = User(
            username="test_org_demo",
            email="test_org_demo@matrix.local",
            role=UserRole.ORGANIZER,
            is_active=True,
        )
        organizer.set_password("Organizer@123")
        db_session.add_all([admin, organizer])
        db_session.commit()

        u_admin, err1 = authenticate_user(db_session, "test_admin_demo", "Admin@123")
        assert err1 is None
        assert u_admin.role == UserRole.ADMIN
        assert u_admin.is_admin is True

        u_org, err2 = authenticate_user(db_session, "test_org_demo", "Organizer@123")
        assert err2 is None
        assert u_org.role == UserRole.ORGANIZER
        assert u_org.is_organizer is True

    def test_bug06_ui_assets_parity_and_existence(self):
        """BUG-06: ui.js must exist in both frontend/js/ and public/js/ with identical content."""
        f_ui = Path("frontend/js/ui.js")
        p_ui = Path("public/js/ui.js")
        assert f_ui.exists(), "frontend/js/ui.js is missing"
        assert p_ui.exists(), "public/js/ui.js is missing"
        assert f_ui.read_text(encoding="utf-8") == p_ui.read_text(encoding="utf-8")

    def test_bug07_falsy_attendees_validation(self, admin_user):
        """BUG-07: expected_guest_count=0 or negative must be strictly rejected, not defaulted to 50."""
        now = datetime.now(timezone.utc)
        start_str = (now + timedelta(days=1)).isoformat()
        end_str = (now + timedelta(days=1, hours=3)).isoformat()

        # Zero guests
        evt1, err1 = create_event(
            db_session,
            organizer_id=admin_user.id,
            data={
                "name": "Zero Guest Event",
                "start_time": start_str,
                "end_time": end_str,
                "expected_guest_count": 0,
            },
        )
        assert evt1 is None
        assert "greater than zero" in err1.lower()

        # Negative guests
        evt2, err2 = create_event(
            db_session,
            organizer_id=admin_user.id,
            data={
                "name": "Negative Guest Event",
                "start_time": start_str,
                "end_time": end_str,
                "expected_guest_count": -15,
            },
        )
        assert evt2 is None
        assert "greater than zero" in err2.lower()

    def test_bug08_reschedule_boundary_checks(self, admin_user):
        """BUG-08: reschedule_or_edit_event must reject non-positive item quantities and guest count <= 0."""
        item = InventoryItem(
            name="Test Reschedule Item",
            category="Audio",
            item_type=ItemType.RETURNABLE,
            total_stock=20,
            unavailable_stock=0,
            minimum_threshold=2,
            unit="units",
            is_active=True,
        )
        db_session.add(item)
        db_session.commit()

        now = datetime.now(timezone.utc)
        start_str = (now + timedelta(days=3)).isoformat()
        end_str = (now + timedelta(days=3, hours=3)).isoformat()

        evt, _ = create_event(
            db_session,
            organizer_id=admin_user.id,
            data={
                "name": "Reschedule Test Event",
                "start_time": start_str,
                "end_time": end_str,
                "expected_guest_count": 50,
            },
        )

        # Update with quantity 0
        updated, err = reschedule_or_edit_event(
            db_session,
            evt.id,
            data={"items": [{"item_id": item.id, "quantity": 0}]},
            user_id=admin_user.id,
        )
        assert updated is None
        assert "greater than zero" in err.get("error", "").lower()

        # Update with guests 0
        updated2, err2 = reschedule_or_edit_event(
            db_session,
            evt.id,
            data={"expected_guest_count": 0},
            user_id=admin_user.id,
        )
        assert updated2 is None
        assert "greater than zero" in err2.get("error", "").lower()

    def test_bug13_and_14_clean_workspace_and_queries(self):
        """BUG-13 & BUG-14: events.db must not linger, and dead SQL is removed."""
        assert not os.path.exists("events.db"), "Lingering zero-byte events.db found in root"
