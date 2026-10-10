"""
Automated tests for Reporting & Dashboard Engine.
Validates:
Test #16: Dashboard values match database (computed, not hardcoded).
"""

from datetime import datetime, timezone, timedelta
from backend.models.base import db_session
from backend.models.inventory import InventoryItem, ItemType
from backend.models.event import Event, EventItem, EventStatus, EventType


def test_test16_dashboard_values_match_database(admin_client, organizer_client, admin_user, organizer_user, sample_chair):
    """
    Test #16: Dashboard summary values must exactly match live database computations.
    Never returns hardcoded or stale placeholder values.
    """
    # 1. Inspect initial state with 1 sample chair (total=100, unavailable=0, threshold=10)
    resp = admin_client.get("/api/reports/dashboard-summary")
    assert resp.status_code == 200, f"Dashboard summary failed: {resp.get_json()}"
    data = resp.get_json()

    assert data["inventory"]["total_items_count"] == 1
    assert data["inventory"]["total_physical_stock"] == 100
    assert data["inventory"]["total_unavailable_stock"] == 0
    assert data["inventory"]["items_at_risk_count"] == 0
    assert data["events"]["total_events_count"] == 0
    assert data["events"]["upcoming_confirmed_count"] == 0

    # 2. Add a second item that is AT RISK (total=5, min_threshold=10)
    low_mic = InventoryItem(
        name="Conference Mic",
        category="Audio",
        item_type=ItemType.RETURNABLE,
        total_stock=5,
        unavailable_stock=0,
        minimum_threshold=10,
        unit="pieces",
        is_active=True,
    )
    db_session.add(low_mic)
    db_session.commit()

    # 3. Add an event in CONFIRMED status in the future
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    future_event = Event(
        organizer_id=organizer_user.id,
        name="Annual Gala 2026",
        event_type=EventType.CORPORATE,
        start_time=now + timedelta(days=2),
        end_time=now + timedelta(days=2, hours=5),
        status=EventStatus.CONFIRMED,
        expected_guest_count=120,
    )
    db_session.add(future_event)
    db_session.flush()

    evt_item = EventItem(
        event_id=future_event.id,
        item_id=sample_chair.id,
        quantity=50,
    )
    db_session.add(evt_item)
    db_session.commit()

    # 4. Fetch dashboard summary as admin and verify exact database calculations
    resp = admin_client.get("/api/reports/dashboard-summary")
    assert resp.status_code == 200
    admin_data = resp.get_json()

    # Database verification
    db_active_count = db_session.query(InventoryItem).filter(InventoryItem.is_active.is_(True)).count()
    assert admin_data["inventory"]["total_items_count"] == db_active_count == 2
    assert admin_data["inventory"]["total_physical_stock"] == 105
    assert admin_data["inventory"]["items_at_risk_count"] == 1
    assert admin_data["inventory"]["items_at_risk"][0]["name"] == "Conference Mic"

    assert admin_data["events"]["total_events_count"] == 1
    assert admin_data["events"]["upcoming_confirmed_count"] == 1
    assert len(admin_data["events"]["recent_events"]) == 1
    assert admin_data["events"]["recent_events"][0]["name"] == "Annual Gala 2026"

    # Category distribution breakdown verification
    categories = {c["category"]: c["total_stock"] for c in admin_data["inventory"]["category_distribution"]}
    assert categories["Chairs"] == 100
    assert categories["Audio"] == 5

    # 5. Verify live reactivity: mark 95 chairs as unavailable (damaged), causing Chairs to also be at risk!
    chair = db_session.query(InventoryItem).filter(InventoryItem.id == sample_chair.id).first()
    chair.unavailable_stock = 95
    db_session.commit()

    resp = admin_client.get("/api/reports/dashboard-summary")
    updated_data = resp.get_json()
    assert updated_data["inventory"]["total_unavailable_stock"] == 95
    # Now BOTH items are at risk:
    # Chairs: 100 - 95 = 5 (<= threshold 10)
    # Mic: 5 - 0 = 5 (<= threshold 10)
    assert updated_data["inventory"]["items_at_risk_count"] == 2


def test_dashboard_organizer_role_isolation(organizer_client, admin_user, organizer_user, sample_chair):
    """
    Verifies that organizers only see their own event totals and bookings,
    adhering to Role-Based Access Control.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Event belonging to admin
    admin_evt = Event(
        organizer_id=admin_user.id,
        name="Admin Private Event",
        event_type=EventType.OTHER,
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=3),
        status=EventStatus.CONFIRMED,
        expected_guest_count=20,
    )
    # Event belonging to organizer
    org_evt = Event(
        organizer_id=organizer_user.id,
        name="Organizer Workshop",
        event_type=EventType.CONFERENCE,
        start_time=now + timedelta(days=3),
        end_time=now + timedelta(days=3, hours=4),
        status=EventStatus.CONFIRMED,
        expected_guest_count=45,
    )
    db_session.add_all([admin_evt, org_evt])
    db_session.commit()

    # Organizer fetches dashboard
    resp = organizer_client.get("/api/reports/dashboard-summary")
    assert resp.status_code == 200
    data = resp.get_json()

    # Organizer should only see 1 event (their own)
    assert data["events"]["total_events_count"] == 1
    assert data["events"]["upcoming_confirmed_count"] == 1
    assert len(data["events"]["recent_events"]) == 1
    assert data["events"]["recent_events"][0]["name"] == "Organizer Workshop"
