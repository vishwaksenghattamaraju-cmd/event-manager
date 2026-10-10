"""Automated tests for booking engine, double-booking prevention, and event rules."""

import pytest
from datetime import datetime, timezone, timedelta
from backend.models.base import db_session
from backend.models.inventory import InventoryItem, ItemType
from backend.models.event import Event, EventStatus


@pytest.fixture
def chairs_item(app, admin_user):
    """Creates a sample item with exactly 100 total stock."""
    with app.app_context():
        item = InventoryItem(
            name="Folding Chairs",
            category="Chairs",
            item_type=ItemType.RETURNABLE,
            total_stock=100,
            unavailable_stock=0,
            minimum_threshold=5,
            unit="pieces",
            is_active=True,
        )
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)
        return item


@pytest.fixture
def napkins_consumable(app, admin_user):
    """Creates a consumable item with 50 total stock."""
    with app.app_context():
        item = InventoryItem(
            name="Paper Napkins Pack",
            category="Consumables",
            item_type=ItemType.CONSUMABLE,
            total_stock=50,
            unavailable_stock=0,
            minimum_threshold=5,
            unit="packs",
            is_active=True,
        )
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)
        return item


def test_organizer_cannot_see_another_organizers_event(app, organizer_user, other_organizer_user):
    """Test 4: An organizer can never view another organizer's events."""
    c1 = app.test_client()
    c1.post("/api/auth/login", json={"username": organizer_user.username, "password": "OrganizerPass123!"})

    c2 = app.test_client()
    c2.post("/api/auth/login", json={"username": other_organizer_user.username, "password": "OtherPass123!"})

    # Organizer 1 creates an event
    now = datetime.now(timezone.utc)
    create_resp = c1.post(
        "/api/events",
        json={
            "name": "Organizer 1 Private Event",
            "start_time": (now + timedelta(days=2)).isoformat(),
            "end_time": (now + timedelta(days=2, hours=4)).isoformat(),
            "expected_guest_count": 50,
        },
    )
    assert create_resp.status_code == 201
    event_id = create_resp.get_json()["event"]["id"]

    # Organizer 2 attempts to get Organizer 1's event -> 403 Forbidden
    resp = c2.get(f"/api/events/{event_id}")
    assert resp.status_code == 403
    assert "Forbidden" in resp.get_json()["error"]

    # Organizer 2 lists events -> does NOT contain Organizer 1's event
    list_resp = c2.get("/api/events")
    assert list_resp.status_code == 200
    listed_ids = [e["id"] for e in list_resp.get_json()["events"]]
    assert event_id not in listed_ids


def test_booking_succeeds_when_stock_is_sufficient(organizer_client, chairs_item):
    """Test 6: Booking succeeds when requested quantity <= available stock."""
    now = datetime.now(timezone.utc)
    start_time = (now + timedelta(days=5, hours=10)).isoformat()
    end_time = (now + timedelta(days=5, hours=14)).isoformat()

    # 1. Create draft event with 60 chairs (available: 100)
    create_resp = organizer_client.post(
        "/api/events",
        json={
            "name": "Corporate Seminar",
            "start_time": start_time,
            "end_time": end_time,
            "items": [{"item_id": chairs_item.id, "quantity": 60}],
        },
    )
    assert create_resp.status_code == 201
    event_id = create_resp.get_json()["event"]["id"]

    # 2. Confirm booking
    confirm_resp = organizer_client.post(f"/api/events/{event_id}/confirm")
    assert confirm_resp.status_code == 200
    confirmed_data = confirm_resp.get_json()["event"]
    assert confirmed_data["status"] == "confirmed"


def test_booking_rejected_when_quantity_exceeds_available(organizer_client, chairs_item):
    """Test 7: Booking is rejected when quantity > available with exact numbers and suggested action."""
    now = datetime.now(timezone.utc)
    start_time = (now + timedelta(days=6, hours=10)).isoformat()
    end_time = (now + timedelta(days=6, hours=14)).isoformat()

    # Total chairs = 100. Request 120.
    create_resp = organizer_client.post(
        "/api/events",
        json={
            "name": "Massive Festival",
            "start_time": start_time,
            "end_time": end_time,
            "items": [{"item_id": chairs_item.id, "quantity": 120}],
        },
    )
    assert create_resp.status_code == 201
    event_id = create_resp.get_json()["event"]["id"]

    confirm_resp = organizer_client.post(f"/api/events/{event_id}/confirm")
    assert confirm_resp.status_code == 409
    err_data = confirm_resp.get_json()
    assert "Insufficient stock" in err_data["error"]
    assert len(err_data["shortages"]) == 1

    shortage = err_data["shortages"][0]
    assert shortage["requested"] == 120
    assert shortage["available"] == 100
    assert shortage["short_by"] == 20
    assert "suggested_action" in shortage
    assert "Reduce quantity" in shortage["suggested_action"]


def test_overlapping_events_cannot_exceed_total_stock(organizer_client, chairs_item):
    """Test 8: Overlapping events cannot together exceed total stock."""
    now = datetime.now(timezone.utc)
    # Event A: 10:00 to 14:00 (reserves 70 chairs)
    start_a = (now + timedelta(days=7, hours=10)).isoformat()
    end_a = (now + timedelta(days=7, hours=14)).isoformat()

    # Event B: 12:00 to 16:00 (overlaps Event A between 12:00 and 14:00, requests 50 chairs)
    # Total needed = 70 + 50 = 120 > 100 -> Event B MUST be rejected!
    start_b = (now + timedelta(days=7, hours=12)).isoformat()
    end_b = (now + timedelta(days=7, hours=16)).isoformat()

    # Create and confirm Event A
    r_a = organizer_client.post(
        "/api/events",
        json={"name": "Event A", "start_time": start_a, "end_time": end_a, "items": [{"item_id": chairs_item.id, "quantity": 70}]},
    )
    event_a_id = r_a.get_json()["event"]["id"]
    conf_a = organizer_client.post(f"/api/events/{event_a_id}/confirm")
    assert conf_a.status_code == 200

    # Create and attempt to confirm Event B
    r_b = organizer_client.post(
        "/api/events",
        json={"name": "Event B", "start_time": start_b, "end_time": end_b, "items": [{"item_id": chairs_item.id, "quantity": 50}]},
    )
    event_b_id = r_b.get_json()["event"]["id"]
    conf_b = organizer_client.post(f"/api/events/{event_b_id}/confirm")
    assert conf_b.status_code == 409
    shortage = conf_b.get_json()["shortages"][0]
    assert shortage["requested"] == 50
    assert shortage["available"] == 30  # 100 - 70 = 30 left!
    assert shortage["short_by"] == 20


def test_cancelling_confirmed_booking_releases_stock(organizer_client, chairs_item):
    """Test 10: Cancelling a confirmed booking releases stock immediately."""
    now = datetime.now(timezone.utc)
    start_time = (now + timedelta(days=8, hours=10)).isoformat()
    end_time = (now + timedelta(days=8, hours=14)).isoformat()

    # Event 1 books all 100 chairs
    r1 = organizer_client.post(
        "/api/events",
        json={"name": "Event 1", "start_time": start_time, "end_time": end_time, "items": [{"item_id": chairs_item.id, "quantity": 100}]},
    )
    event1_id = r1.get_json()["event"]["id"]
    organizer_client.post(f"/api/events/{event1_id}/confirm")

    # Event 2 attempts to book 20 chairs for same window -> rejected (available = 0)
    r2 = organizer_client.post(
        "/api/events",
        json={"name": "Event 2", "start_time": start_time, "end_time": end_time, "items": [{"item_id": chairs_item.id, "quantity": 20}]},
    )
    event2_id = r2.get_json()["event"]["id"]
    rej_resp = organizer_client.post(f"/api/events/{event2_id}/confirm")
    assert rej_resp.status_code == 409

    # Cancel Event 1
    cancel_resp = organizer_client.post(f"/api/events/{event1_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.get_json()["event"]["status"] == "cancelled"

    # Now Event 2 can be confirmed successfully!
    succ_resp = organizer_client.post(f"/api/events/{event2_id}/confirm")
    assert succ_resp.status_code == 200
    assert succ_resp.get_json()["event"]["status"] == "confirmed"


def test_editing_or_rescheduling_triggers_availability_check(organizer_client, chairs_item):
    """Test 11: Editing/rescheduling triggers availability check; a failed edit changes nothing."""
    now = datetime.now(timezone.utc)
    # Window 1: Day 9, 10:00 to 14:00 (Event A books 80 chairs)
    start_1 = (now + timedelta(days=9, hours=10)).isoformat()
    end_1 = (now + timedelta(days=9, hours=14)).isoformat()

    # Window 2: Day 9, 16:00 to 20:00 (Event B books 50 chairs)
    start_2 = (now + timedelta(days=9, hours=16)).isoformat()
    end_2 = (now + timedelta(days=9, hours=20)).isoformat()

    # Confirm Event A (80 chairs at Window 1)
    r_a = organizer_client.post(
        "/api/events",
        json={"name": "Event A", "start_time": start_1, "end_time": end_1, "items": [{"item_id": chairs_item.id, "quantity": 80}]},
    )
    event_a_id = r_a.get_json()["event"]["id"]
    organizer_client.post(f"/api/events/{event_a_id}/confirm")

    # Confirm Event B (50 chairs at Window 2)
    r_b = organizer_client.post(
        "/api/events",
        json={"name": "Event B", "start_time": start_2, "end_time": end_2, "items": [{"item_id": chairs_item.id, "quantity": 50}]},
    )
    event_b_id = r_b.get_json()["event"]["id"]
    organizer_client.post(f"/api/events/{event_b_id}/confirm")

    # Try to reschedule Event B to Window 1 (10:00 to 14:00) with 50 chairs
    # Window 1 only has 20 chairs available (100 - 80). Event B needs 50. Must fail!
    edit_resp = organizer_client.put(
        f"/api/events/{event_b_id}",
        json={"start_time": start_1, "end_time": end_1},
    )
    assert edit_resp.status_code == 409
    assert "Insufficient stock" in edit_resp.get_json()["error"]

    # Verify Event B's schedule was NOT changed (clean rollback!)
    b_check = organizer_client.get(f"/api/events/{event_b_id}").get_json()["event"]
    assert datetime.fromisoformat(b_check["start_time"]).replace(tzinfo=timezone.utc) == datetime.fromisoformat(start_2)
    assert datetime.fromisoformat(b_check["end_time"]).replace(tzinfo=timezone.utc) == datetime.fromisoformat(end_2)


def test_adjacent_events_do_not_conflict(organizer_client, chairs_item):
    """Test 12: Adjacent events (one ends exactly when next starts) do NOT conflict [start, end)."""
    now = datetime.now(timezone.utc)
    t1 = (now + timedelta(days=10, hours=10)).isoformat()
    t2 = (now + timedelta(days=10, hours=14)).isoformat()
    t3 = (now + timedelta(days=10, hours=18)).isoformat()

    # Event 1: [10:00, 14:00) books ALL 100 chairs
    r1 = organizer_client.post(
        "/api/events",
        json={"name": "Morning Conference", "start_time": t1, "end_time": t2, "items": [{"item_id": chairs_item.id, "quantity": 100}]},
    )
    e1_id = r1.get_json()["event"]["id"]
    conf1 = organizer_client.post(f"/api/events/{e1_id}/confirm")
    assert conf1.status_code == 200

    # Event 2: [14:00, 18:00) starts EXACTLY at 14:00 and books ALL 100 chairs
    # Half-open rule: 14:00 does not overlap with [10:00, 14:00). Both MUST succeed!
    r2 = organizer_client.post(
        "/api/events",
        json={"name": "Evening Gala", "start_time": t2, "end_time": t3, "items": [{"item_id": chairs_item.id, "quantity": 100}]},
    )
    e2_id = r2.get_json()["event"]["id"]
    conf2 = organizer_client.post(f"/api/events/{e2_id}/confirm")
    assert conf2.status_code == 200, f"Adjacent event failed: {conf2.get_json()}"


def test_draft_and_cancelled_events_do_not_consume_stock(organizer_client, chairs_item):
    """Test 13: Draft and cancelled events do NOT consume stock."""
    now = datetime.now(timezone.utc)
    t_start = (now + timedelta(days=11, hours=10)).isoformat()
    t_end = (now + timedelta(days=11, hours=14)).isoformat()

    # 1. Create a DRAFT event with 100 chairs
    r_draft = organizer_client.post(
        "/api/events",
        json={"name": "Draft Event", "start_time": t_start, "end_time": t_end, "items": [{"item_id": chairs_item.id, "quantity": 100}]},
    )
    assert r_draft.status_code == 201

    # 2. Check preview availability: available stock MUST still be 100!
    prev_resp = organizer_client.post(
        "/api/events/check-availability",
        json={"start_time": t_start, "end_time": t_end, "items": [{"item_id": chairs_item.id, "quantity": 100}]},
    )
    assert prev_resp.status_code == 200
    assert prev_resp.get_json()["is_sufficient"] is True
    assert prev_resp.get_json()["item_statuses"][0]["available_stock"] == 100


def test_double_clicking_confirm_does_not_double_allocate(organizer_client, chairs_item):
    """Test 14: Double-clicking confirm is idempotent and does not create duplicate allocations."""
    now = datetime.now(timezone.utc)
    t_start = (now + timedelta(days=12, hours=10)).isoformat()
    t_end = (now + timedelta(days=12, hours=14)).isoformat()

    r = organizer_client.post(
        "/api/events",
        json={"name": "Idempotent Event", "start_time": t_start, "end_time": t_end, "items": [{"item_id": chairs_item.id, "quantity": 50}]},
    )
    event_id = r.get_json()["event"]["id"]

    # Click 1
    conf1 = organizer_client.post(
        f"/api/events/{event_id}/confirm",
        json={"idempotency_key": "idemp-key-12345"},
    )
    assert conf1.status_code == 200

    # Click 2 (Simulated duplicate submit / double click)
    conf2 = organizer_client.post(
        f"/api/events/{event_id}/confirm",
        json={"idempotency_key": "idemp-key-12345"},
    )
    assert conf2.status_code == 200

    # Verify directly: event items must still have quantity = 50, not 100
    event_in_db = db_session.query(Event).filter(Event.id == event_id).first()
    assert len(event_in_db.items) == 1
    assert event_in_db.items[0].quantity == 50


def test_complete_event_consumables_deduction(organizer_client, napkins_consumable, chairs_item):
    """Test Completing an event permanently deducts consumable items and releases returnable items."""
    now = datetime.now(timezone.utc)
    t_start = (now + timedelta(days=13, hours=10)).isoformat()
    t_end = (now + timedelta(days=13, hours=14)).isoformat()

    r = organizer_client.post(
        "/api/events",
        json={
            "name": "Wedding Dinner",
            "start_time": t_start,
            "end_time": t_end,
            "items": [
                {"item_id": chairs_item.id, "quantity": 40},
                {"item_id": napkins_consumable.id, "quantity": 15},
            ],
        },
    )
    event_id = r.get_json()["event"]["id"]
    organizer_client.post(f"/api/events/{event_id}/confirm")

    # Complete the event
    comp_resp = organizer_client.post(f"/api/events/{event_id}/complete")
    assert comp_resp.status_code == 200
    assert comp_resp.get_json()["event"]["status"] == "completed"

    # Consumable napkins: initial 50 - 15 used = 35 total stock remaining
    updated_napkins = db_session.query(InventoryItem).filter_by(id=napkins_consumable.id).first()
    assert updated_napkins.total_stock == 35

    # Returnable chairs: total stock is still 100!
    updated_chairs = db_session.query(InventoryItem).filter_by(id=chairs_item.id).first()
    assert updated_chairs.total_stock == 100
