"""Event service: CRUD operations, organizer data isolation, and input validation."""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.models.user import User, UserRole
from backend.models.event import Event, EventItem, EventStatus, EventType
from backend.models.inventory import InventoryItem


def parse_datetime_utc(dt_val: Any) -> datetime:
    """Parses ISO8601 strings or datetime objects into a timezone-naive UTC datetime."""
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is not None:
            return dt_val.astimezone(timezone.utc).replace(tzinfo=None)
        return dt_val
    if isinstance(dt_val, str):
        # Handle trailing Z or offset
        cleaned = dt_val.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    raise ValueError(f"Invalid datetime format: {dt_val}")


def create_event(
    db: Session,
    organizer_id: int,
    data: Dict[str, Any],
) -> Tuple[Optional[Event], Optional[str]]:
    """
    Creates a new Event in DRAFT status with required items.
    """
    name = (data.get("name") or data.get("title") or "").strip()
    if not name:
        return None, "Event name is required."

    event_type = (data.get("event_type") or EventType.OTHER).strip().lower()
    if event_type not in EventType.ALL_TYPES:
        event_type = EventType.OTHER

    try:
        start_time = parse_datetime_utc(data.get("start_time"))
        end_time = parse_datetime_utc(data.get("end_time"))
    except Exception as e:
        return None, f"Invalid start or end datetime: {str(e)}"

    if start_time >= end_time:
        return None, "Event start time must precede end time."

    try:
        expected_guests = int(data.get("expected_guest_count") or data.get("expected_attendees") or 50)
        if expected_guests <= 0:
            return None, "Expected guest count must be greater than zero."

        setup_buffer = int(data.get("setup_buffer_minutes", 0))
        teardown_buffer = int(data.get("teardown_buffer_minutes", 0))
        if setup_buffer < 0 or teardown_buffer < 0:
            return None, "Buffer minutes cannot be negative."

        event = Event(
            organizer_id=organizer_id,
            name=name,
            event_type=event_type,
            location=(data.get("location") or "").strip() or None,
            start_time=start_time,
            end_time=end_time,
            setup_buffer_minutes=setup_buffer,
            teardown_buffer_minutes=teardown_buffer,
            expected_guest_count=expected_guests,
            status=EventStatus.DRAFT,
        )
        db.add(event)
        db.flush()

        # Add items if provided
        items_data = data.get("items", [])
        for item_entry in items_data:
            item_id = int(item_entry.get("item_id") or item_entry.get("inventory_item_id"))
            quantity = int(item_entry.get("quantity") or item_entry.get("quantity_requested"))

            if quantity <= 0:
                db.rollback()
                return None, f"Item quantity must be greater than zero."

            # Verify item exists
            item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
            if not item:
                db.rollback()
                return None, f"Inventory item with ID {item_id} not found."

            event_item = EventItem(
                event_id=event.id,
                item_id=item_id,
                quantity=quantity,
            )
            db.add(event_item)

        db.commit()
        db.refresh(event)
        return event, None

    except ValueError as e:
        db.rollback()
        return None, f"Validation error: {str(e)}"
    except Exception as e:
        db.rollback()
        return None, f"Failed to create event: {str(e)}"


def get_events(
    db: Session,
    user: User,
    status: Optional[str] = None,
) -> List[Event]:
    """
    Returns events adhering to Role-Based Access Control:
    - Administrator sees all events.
    - Organizer sees ONLY their own events.
    """
    query = db.query(Event)

    if not user.is_admin:
        # Enforce strict data isolation: organizer sees only own events
        query = query.filter(Event.organizer_id == user.id)

    if status:
        query = query.filter(Event.status == status.strip().lower())

    return query.order_by(Event.start_time.asc()).all()


def get_event_by_id(
    db: Session,
    event_id: int,
    user: User,
) -> Tuple[Optional[Event], Optional[str]]:
    """
    Retrieves a single event by ID with authorization verification:
    - Returns error if an organizer attempts to view another organizer's event.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return None, "Event not found."

    if not user.is_admin and event.organizer_id != user.id:
        return None, "Forbidden: You do not have permission to view this event."

    return event, None
