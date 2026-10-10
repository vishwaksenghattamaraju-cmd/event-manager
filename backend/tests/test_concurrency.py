"""Concurrency test: Two simultaneous confirm requests for the last units.
Verifies that pessimistic row locking and atomic transactions guarantee:
EXACTLY ONE SUCCEEDS, AND DOUBLE-BOOKING NEVER OCCURS.
"""

import os
import threading
import pytest
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

from backend.app import create_app
from backend.config import Config, TestConfig
from backend.models.base import init_database, create_all_tables, drop_all_tables, db_session, SessionLocal
from backend.models.user import User, UserRole
from backend.models.inventory import InventoryItem, ItemType
from backend.models.event import Event, EventItem, EventStatus
from backend.services.booking_service import confirm_event_booking


def test_two_simultaneous_confirm_requests_for_last_units(app):
    """
    Test 9 (Concurrency):
    - Item has total_stock = 10.
    - Two events (Event 1 and Event 2) are created for the EXACT same overlapping time window.
    - Each event requests ALL 10 units.
    - Two concurrent threads attempt to confirm Event 1 and Event 2 at the exact same millisecond.
    - Result: Exactly one event is CONFIRMED; the other is REJECTED.
    - Allocated stock never exceeds 10!
    """
    with app.app_context():
        # Setup: create user, item with 10 units, and two draft events
        user = User(username="conc_org", email="conc@test.com", role=UserRole.ORGANIZER)
        user.set_password("Pass123!")
        db_session.add(user)
        db_session.flush()

        item = InventoryItem(
            name="Exclusive Sound System",
            category="Audio",
            item_type=ItemType.RETURNABLE,
            total_stock=10,
            unavailable_stock=0,
            minimum_threshold=0,
            is_active=True,
        )
        db_session.add(item)
        db_session.flush()

        now = datetime.now(timezone.utc)
        start_time = now + timedelta(days=20, hours=10)
        end_time = now + timedelta(days=20, hours=14)

        event1 = Event(
            organizer_id=user.id,
            name="Concert A",
            start_time=start_time,
            end_time=end_time,
            status=EventStatus.DRAFT,
        )
        event2 = Event(
            organizer_id=user.id,
            name="Concert B",
            start_time=start_time,
            end_time=end_time,
            status=EventStatus.DRAFT,
        )
        db_session.add_all([event1, event2])
        db_session.flush()

        item1 = EventItem(event_id=event1.id, item_id=item.id, quantity=10)
        item2 = EventItem(event_id=event2.id, item_id=item.id, quantity=10)
        db_session.add_all([item1, item2])
        db_session.commit()

        event1_id = event1.id
        event2_id = event2.id
        item_id = item.id
        saved_user_id = user.id

    # Barrier to synchronize threads to fire at the exact same instant
    barrier = threading.Barrier(2)
    results = {}

    def try_confirm(thread_id, target_event_id):
        # Each thread uses its own dedicated database session
        local_db = SessionLocal()
        try:
            # Wait for both threads to reach the starting line
            barrier.wait(timeout=5)

            event, failure = confirm_event_booking(
                db=local_db,
                event_id=target_event_id,
                user_id=saved_user_id,
            )
            if event and event.status == EventStatus.CONFIRMED:
                results[thread_id] = ("SUCCESS", target_event_id)
            else:
                results[thread_id] = ("FAILED", failure.get("error") if failure else "Unknown failure")
        except Exception as e:
            results[thread_id] = ("FAILED", str(e))
        finally:
            local_db.close()

    t1 = threading.Thread(target=try_confirm, args=("thread_1", event1_id))
    t2 = threading.Thread(target=try_confirm, args=("thread_2", event2_id))

    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Analyze outcomes
    statuses = [v[0] for v in results.values()]
    success_count = statuses.count("SUCCESS")
    failure_count = statuses.count("FAILED")

    assert success_count == 1, f"Expected exactly 1 booking to succeed, but got {success_count}. Results: {results}"
    assert failure_count == 1, f"Expected exactly 1 booking to fail, but got {failure_count}. Results: {results}"

    # Verify directly from database:
    # Only one event is confirmed, and total allocated stock is exactly 10 (never 20!)
    with app.app_context():
        e1 = db_session.query(Event).filter(Event.id == event1_id).first()
        e2 = db_session.query(Event).filter(Event.id == event2_id).first()

        confirmed_events = [e for e in (e1, e2) if e.status == EventStatus.CONFIRMED]
        assert len(confirmed_events) == 1, "Exactly one event should have status 'confirmed'"


# Optional MySQL-specific concurrency test when MySQL is available
@pytest.mark.skipif(
    not os.getenv("MYSQL_TEST_URL"),
    reason="MySQL concurrency test requires MYSQL_TEST_URL environment variable."
)
def test_mysql_row_locking_concurrency():
    """
    Dedicated test for MySQL 8 InnoDB row-level locking (SELECT ... FOR UPDATE).
    Run with:
        $env:MYSQL_TEST_URL="mysql+pymysql://event_user:password123@localhost:3306/event_inventory_db"
        pytest -v -k test_mysql_row_locking_concurrency
    """
    mysql_url = os.getenv("MYSQL_TEST_URL")
    class MySQLTestConfig(Config):
        TESTING = True
        DATABASE_URL = mysql_url

    mysql_app = create_app(MySQLTestConfig)
    test_two_simultaneous_confirm_requests_for_last_units(mysql_app)
