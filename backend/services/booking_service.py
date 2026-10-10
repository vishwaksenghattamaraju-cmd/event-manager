import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

# Mutex to ensure atomicity for concurrency on engines without native row locks (like SQLite)
# On MySQL InnoDB, SELECT ... FOR UPDATE provides row-level locking across processes.
_booking_lock = threading.RLock()

from backend.models.inventory import (
    InventoryItem,
    InventoryTransaction,
    ItemType,
    TransactionType,
)
from backend.models.event import (
    Event,
    EventItem,
    EventStatus,
)
from backend.services.alert_service import check_and_create_stock_alert


def get_effective_window(
    start_time: datetime,
    end_time: datetime,
    setup_buffer_minutes: int = 0,
    teardown_buffer_minutes: int = 0,
) -> Tuple[datetime, datetime]:
    """
    Computes the effective occupied window [eff_start, eff_end)
    extended by setup and teardown buffer times.
    """
    eff_start = start_time - timedelta(minutes=setup_buffer_minutes)
    eff_end = end_time + timedelta(minutes=teardown_buffer_minutes)
    return eff_start, eff_end


def check_item_availability_for_window(
    db: Session,
    item_id: int,
    req_start: datetime,
    req_end: datetime,
    setup_buffer_minutes: int = 0,
    teardown_buffer_minutes: int = 0,
    exclude_event_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Calculates stock availability for an item during the requested window [req_start, req_end).

    GOLDEN RULE (Half-open intervals):
    Two events overlap if and only if:
        existing_start < requested_end AND existing_end > requested_start

    Stock formula:
        available(item, window) = total_stock
                                  - unavailable_stock
                                  - SUM(quantity allocated by CONFIRMED events that overlap window)
    """
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise ValueError(f"Inventory item with ID {item_id} not found.")

    eff_req_start, eff_req_end = get_effective_window(
        req_start, req_end, setup_buffer_minutes, teardown_buffer_minutes
    )

    # Query all confirmed events that overlap the requested effective window
    # Overlap condition:
    # (event.start_time - setup_buffer) < eff_req_end AND (event.end_time + teardown_buffer) > eff_req_start
    query = (
        db.query(func.coalesce(func.sum(EventItem.quantity), 0))
        .join(Event, Event.id == EventItem.event_id)
        .filter(
            EventItem.item_id == item_id,
            Event.status == EventStatus.CONFIRMED,
            # Half-open interval overlap check
            # existing_effective_start < requested_effective_end
            Event.start_time - func.concat(Event.setup_buffer_minutes, " minute")
            if db.bind and db.bind.dialect.name == "mysql"
            else Event.start_time < eff_req_end,  # Python-evaluated fallback / standard
        )
    )

    # Build dialect-safe overlap query:
    # An event overlaps when (Event.start_time < eff_req_end) AND (Event.end_time > eff_req_start)
    overlap_query = (
        db.query(func.coalesce(func.sum(EventItem.quantity), 0))
        .join(Event, Event.id == EventItem.event_id)
        .filter(
            EventItem.item_id == item_id,
            Event.status == EventStatus.CONFIRMED,
            Event.start_time < eff_req_end,
            Event.end_time > eff_req_start,
        )
    )

    if exclude_event_id:
        overlap_query = overlap_query.filter(Event.id != exclude_event_id)

    allocated_stock = overlap_query.scalar() or 0

    # Stock physically sound
    physically_available = max(0, item.total_stock - item.unavailable_stock)
    # Available for this specific time window
    window_available = max(0, physically_available - allocated_stock)

    return {
        "item_id": item.id,
        "item_name": item.name,
        "item_type": item.item_type,
        "is_active": item.is_active,
        "total_stock": item.total_stock,
        "unavailable_stock": item.unavailable_stock,
        "allocated_stock": allocated_stock,
        "available_stock": window_available,
        "unit": item.unit,
    }


def check_bulk_availability(
    db: Session,
    requirements: List[Dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    setup_buffer_minutes: int = 0,
    teardown_buffer_minutes: int = 0,
    exclude_event_id: Optional[int] = None,
) -> Tuple[bool, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Checks availability across a list of requested items [{'item_id': x, 'quantity': y}].
    Returns:
        (is_sufficient, item_statuses, shortages)
    """
    if start_time >= end_time:
        raise ValueError("Event start time must precede end time.")

    is_sufficient = True
    item_statuses = []
    shortages = []

    for req in requirements:
        item_id = int(req.get("item_id") or req.get("inventory_item_id"))
        requested_qty = int(req.get("quantity") or req.get("quantity_requested"))

        if requested_qty <= 0:
            raise ValueError(f"Requested quantity for item {item_id} must be greater than zero.")

        avail = check_item_availability_for_window(
            db=db,
            item_id=item_id,
            req_start=start_time,
            req_end=end_time,
            setup_buffer_minutes=setup_buffer_minutes,
            teardown_buffer_minutes=teardown_buffer_minutes,
            exclude_event_id=exclude_event_id,
        )

        avail["requested_quantity"] = requested_qty
        item_statuses.append(avail)

        if not avail["is_active"]:
            is_sufficient = False
            shortages.append({
                "item_id": item_id,
                "item_name": avail["item_name"],
                "requested": requested_qty,
                "available": 0,
                "short_by": requested_qty,
                "suggested_action": "Item has been deactivated. Remove or select an alternative item.",
            })
        elif requested_qty > avail["available_stock"]:
            is_sufficient = False
            short_by = requested_qty - avail["available_stock"]
            shortages.append({
                "item_id": item_id,
                "item_name": avail["item_name"],
                "requested": requested_qty,
                "available": avail["available_stock"],
                "short_by": short_by,
                "suggested_action": (
                    f"Reduce quantity by {short_by}, choose an alternate time window, "
                    f"or add physical stock."
                ),
            })

    return is_sufficient, item_statuses, shortages


def confirm_event_booking(
    db: Session,
    event_id: int,
    user_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> Tuple[Optional[Event], Optional[Dict[str, Any]]]:
    """
    Confirms an event booking inside an atomic database transaction.
    Locks all relevant inventory rows with SELECT ... FOR UPDATE in ascending item_id order.
    Checks live availability AFTER acquiring the lock.
    Rejects cleanly if stock is insufficient.
    """
    with _booking_lock:
        # 1. Fetch event
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            return None, {"error": "Event not found."}

        # Idempotency check: if already confirmed with the same idempotency key, return successfully
        if event.status == EventStatus.CONFIRMED:
            if idempotency_key and event.idempotency_key == idempotency_key:
                return event, None
            return event, None  # Re-confirming already confirmed event is idempotent

        if event.status in (EventStatus.CANCELLED, EventStatus.COMPLETED):
            return None, {
                "error": f"Cannot confirm an event that has status '{event.status}'."
            }

        if not event.items:
            return None, {"error": "Event has no items to book."}

        # 2. Acquire lock on inventory items in deterministic ASCENDING order to avoid deadlocks
        item_ids = sorted(list({item.item_id for item in event.items}))

        try:
            # SELECT ... FOR UPDATE on inventory items
            # In MySQL InnoDB, this establishes row-level exclusive locks across processes.
            # In SQLite, it executes within the transaction under _booking_lock.
            locked_items = (
                db.query(InventoryItem)
                .filter(InventoryItem.id.in_(item_ids))
                .order_by(InventoryItem.id.asc())
                .with_for_update()
                .all()
            )

            # 3. Check live availability AFTER acquiring the locks
            requirements = [{"item_id": it.item_id, "quantity": it.quantity} for it in event.items]
            is_sufficient, statuses, shortages = check_bulk_availability(
                db=db,
                requirements=requirements,
                start_time=event.start_time,
                end_time=event.end_time,
                setup_buffer_minutes=event.setup_buffer_minutes,
                teardown_buffer_minutes=event.teardown_buffer_minutes,
                exclude_event_id=event.id,
            )

            if not is_sufficient:
                # Reject booking - stock insufficient!
                db.rollback()
                return None, {
                    "error": "Insufficient stock available for requested time window.",
                    "shortages": shortages,
                    "item_statuses": statuses,
                }

            # 4. Commit the confirmation
            event.status = EventStatus.CONFIRMED
            if idempotency_key:
                event.idempotency_key = idempotency_key

            # Write transaction audit record for the allocation
            for it in event.items:
                tx = InventoryTransaction(
                    item_id=it.item_id,
                    user_id=user_id or event.organizer_id,
                    change_amount=0,  # Physical stock hasn't changed, but is reserved
                    previous_total_stock=it.item.total_stock,
                    new_total_stock=it.item.total_stock,
                    transaction_type=TransactionType.ADJUSTMENT,
                    reason=f"Reserved {it.quantity} units for Event '{event.name}' (ID: {event.id})",
                )
                db.add(tx)

            db.commit()
            db.refresh(event)
            return event, None

        except Exception as e:
            db.rollback()
            return None, {"error": f"Booking confirmation failed: {str(e)}"}


def cancel_event_booking(
    db: Session, event_id: int, user_id: Optional[int] = None
) -> Tuple[Optional[Event], Optional[str]]:
    """
    Cancels a confirmed or draft event.
    Releases allocated stock immediately because only CONFIRMED events count toward stock.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return None, "Event not found."

    if event.status == EventStatus.CANCELLED:
        return event, None  # Idempotent cancel

    if event.status == EventStatus.COMPLETED:
        return None, "Cannot cancel an event that is already completed."

    try:
        previous_status = event.status
        event.status = EventStatus.CANCELLED

        if previous_status == EventStatus.CONFIRMED:
            for it in event.items:
                tx = InventoryTransaction(
                    item_id=it.item_id,
                    user_id=user_id or event.organizer_id,
                    change_amount=0,
                    previous_total_stock=it.item.total_stock,
                    new_total_stock=it.item.total_stock,
                    transaction_type=TransactionType.ADJUSTMENT,
                    reason=f"Released reservation from cancelled Event '{event.name}' (ID: {event.id})",
                )
                db.add(tx)

        db.commit()
        db.refresh(event)
        return event, None
    except Exception as e:
        db.rollback()
        return None, f"Failed to cancel event: {str(e)}"


def reschedule_or_edit_event(
    db: Session,
    event_id: int,
    data: Dict[str, Any],
    user_id: Optional[int] = None,
) -> Tuple[Optional[Event], Optional[Dict[str, Any]]]:
    """
    Reschedules or edits an event.
    If the event is already CONFIRMED:
        Locks inventory rows.
        Re-evaluates availability for the new window/items, EXCLUDING this event's current allocation.
        If stock is insufficient: Fails cleanly with ZERO changes (atomic rollback).
        If sufficient: Updates dates and allocations; commits.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return None, {"error": "Event not found."}

    if event.status in (EventStatus.CANCELLED, EventStatus.COMPLETED):
        return None, {"error": f"Cannot edit an event that is {event.status}."}

    # Parse potential new dates
    new_start = event.start_time
    new_end = event.end_time

    if "start_time" in data and data["start_time"]:
        val = data["start_time"]
        if isinstance(val, str):
            cleaned = val.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(cleaned)
            new_start = parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        else:
            new_start = val

    if "end_time" in data and data["end_time"]:
        val = data["end_time"]
        if isinstance(val, str):
            cleaned = val.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(cleaned)
            new_end = parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        else:
            new_end = val

    if new_start >= new_end:
        return None, {"error": "Event start time must precede end time."}

    new_setup_buffer = data.get("setup_buffer_minutes", event.setup_buffer_minutes)
    new_teardown_buffer = data.get("teardown_buffer_minutes", event.teardown_buffer_minutes)

    # Determine items list
    new_items_spec = data.get("items")
    if new_items_spec is None:
        new_requirements = [{"item_id": it.item_id, "quantity": it.quantity} for it in event.items]
    else:
        new_requirements = [
            {"item_id": int(i["item_id"]), "quantity": int(i["quantity"])}
            for i in new_items_spec
        ]

    # If the event is CONFIRMED, re-run full availability check inside a locked transaction
    if event.status == EventStatus.CONFIRMED:
        all_item_ids = sorted(list({req["item_id"] for req in new_requirements}))

        try:
            # Lock inventory rows in ascending order
            db.query(InventoryItem).filter(InventoryItem.id.in_(all_item_ids)).order_by(
                InventoryItem.id.asc()
            ).with_for_update().all()

            # Check availability excluding this event's own allocation
            is_sufficient, statuses, shortages = check_bulk_availability(
                db=db,
                requirements=new_requirements,
                start_time=new_start,
                end_time=new_end,
                setup_buffer_minutes=new_setup_buffer,
                teardown_buffer_minutes=new_teardown_buffer,
                exclude_event_id=event.id,
            )

            if not is_sufficient:
                db.rollback()
                return None, {
                    "error": "Insufficient stock available for updated schedule/quantities.",
                    "shortages": shortages,
                    "item_statuses": statuses,
                }

            # Apply changes
            event.start_time = new_start
            event.end_time = new_end
            event.setup_buffer_minutes = new_setup_buffer
            event.teardown_buffer_minutes = new_teardown_buffer

            if "name" in data and data["name"]:
                event.name = data["name"].strip()
            if "location" in data:
                event.location = data["location"].strip() if data["location"] else None
            if "expected_guest_count" in data:
                event.expected_guest_count = int(data["expected_guest_count"])

            if new_items_spec is not None:
                # Update item requirements
                event.items.clear()
                for req in new_requirements:
                    db.add(EventItem(event_id=event.id, item_id=req["item_id"], quantity=req["quantity"]))

            db.commit()
            db.refresh(event)
            return event, None

        except Exception as e:
            db.rollback()
            return None, {"error": f"Failed to reschedule event: {str(e)}"}

    else:
        # Event is DRAFT: simple update without locking
        try:
            event.start_time = new_start
            event.end_time = new_end
            event.setup_buffer_minutes = new_setup_buffer
            event.teardown_buffer_minutes = new_teardown_buffer

            if "name" in data and data["name"]:
                event.name = data["name"].strip()
            if "location" in data:
                event.location = data["location"].strip() if data["location"] else None
            if "expected_guest_count" in data:
                event.expected_guest_count = int(data["expected_guest_count"])

            if new_items_spec is not None:
                event.items.clear()
                for req in new_requirements:
                    db.add(EventItem(event_id=event.id, item_id=req["item_id"], quantity=req["quantity"]))

            db.commit()
            db.refresh(event)
            return event, None
        except Exception as e:
            db.rollback()
            return None, {"error": f"Failed to update draft event: {str(e)}"}


def complete_event(
    db: Session, event_id: int, user_id: Optional[int] = None
) -> Tuple[Optional[Event], Optional[str]]:
    """
    Marks an event as COMPLETED.
    Consumable items (e.g., flowers, napkins, confetti) have their used quantities
    permanently deducted from InventoryItem.total_stock via a transaction log.
    Returnable items are simply freed up for future bookings.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return None, "Event not found."

    if event.status != EventStatus.CONFIRMED:
        return None, f"Only confirmed events can be completed. Current status: '{event.status}'."

    try:
        event.status = EventStatus.COMPLETED

        # Process consumable item stock deductions
        for event_item in event.items:
            item = event_item.item
            if item.item_type == ItemType.CONSUMABLE:
                consumed_qty = event_item.quantity
                old_total = item.total_stock
                new_total = max(0, old_total - consumed_qty)
                item.total_stock = new_total

                tx = InventoryTransaction(
                    item_id=item.id,
                    user_id=user_id or event.organizer_id,
                    change_amount=-consumed_qty,
                    previous_total_stock=old_total,
                    new_total_stock=new_total,
                    transaction_type=TransactionType.CONSUMED,
                    reason=f"Consumed {consumed_qty} units during Event '{event.name}' (ID: {event.id})",
                )
                db.add(tx)

        db.commit()
        db.refresh(event)
        for event_item in event.items:
            if event_item.item.item_type == ItemType.CONSUMABLE:
                check_and_create_stock_alert(db, event_item.item_id)
        return event, None
    except Exception as e:
        db.rollback()
        return None, f"Failed to complete event: {str(e)}"
