"""Event and Booking routes: availability checks, event CRUD, confirmation, cancellation."""

from flask import Blueprint, request, jsonify
from backend.models.base import db_session
from backend.routes.auth_routes import login_required, organizer_or_admin_required, get_current_user
from backend.services.event_service import (
    create_event,
    get_events,
    get_event_by_id,
    parse_datetime_utc,
)
from backend.services.booking_service import (
    check_bulk_availability,
    confirm_event_booking,
    cancel_event_booking,
    reschedule_or_edit_event,
    complete_event,
)

event_bp = Blueprint("events", __name__, url_prefix="/api/events")


@event_bp.route("", methods=["GET"])
@organizer_or_admin_required
def list_events():
    """Lists events filtered by status. Organizers see only their own events."""
    user = get_current_user()
    status = request.args.get("status")
    events = get_events(db_session, user=user, status=status)
    return jsonify({
        "events": [event.to_dict(include_items=True) for event in events],
        "count": len(events)
    }), 200


@event_bp.route("/<int:event_id>", methods=["GET"])
@organizer_or_admin_required
def get_event(event_id: int):
    """Retrieves event details. Organizers cannot see events of other organizers."""
    user = get_current_user()
    event, error = get_event_by_id(db_session, event_id, user=user)
    if error:
        status_code = 403 if "Forbidden" in error else 404
        return jsonify({"error": error}), status_code

    return jsonify({"event": event.to_dict(include_items=True)}), 200


@event_bp.route("", methods=["POST"])
@organizer_or_admin_required
def create_new_event():
    """Creates a new event in DRAFT status, with optional immediate confirmation."""
    user = get_current_user()
    data = request.get_json(silent=True) or {}

    event, error = create_event(db_session, organizer_id=user.id, data=data)
    if error:
        return jsonify({"error": error}), 400

    should_confirm = str(data.get("status", "")).upper() == "CONFIRMED" or bool(data.get("confirm", False))
    if should_confirm:
        confirmed_event, failure = confirm_event_booking(
            db=db_session,
            event_id=event.id,
            user_id=user.id,
        )
        if failure:
            return jsonify({
                "error": f"Booking created as draft, but could not be confirmed: {failure.get('error', failure)}",
                "shortages": failure.get("shortages", []),
                "event": event.to_dict(include_items=True)
            }), 409
        event = confirmed_event

    return jsonify({
        "message": "Event created successfully.",
        "event": event.to_dict(include_items=True)
    }), 201


@event_bp.route("/check-availability", methods=["POST"])
@organizer_or_admin_required
def check_availability_preview():
    """
    Previews availability for a requested time window and item quantities
    without modifying or reserving stock.
    """
    data = request.get_json(silent=True) or {}
    start_time_raw = data.get("start_time")
    end_time_raw = data.get("end_time")
    items_raw = data.get("items", [])
    setup_buffer = int(data.get("setup_buffer_minutes", 0))
    teardown_buffer = int(data.get("teardown_buffer_minutes", 0))
    exclude_event_id = data.get("exclude_event_id")

    if not start_time_raw or not end_time_raw:
        return jsonify({"error": "Start time and end time are required."}), 400
    if not items_raw:
        return jsonify({"error": "Items list is required."}), 400

    try:
        start_time = parse_datetime_utc(start_time_raw)
        end_time = parse_datetime_utc(end_time_raw)
    except Exception as e:
        return jsonify({"error": f"Invalid datetime format: {str(e)}"}), 400

    try:
        is_sufficient, item_statuses, shortages = check_bulk_availability(
            db=db_session,
            requirements=items_raw,
            start_time=start_time,
            end_time=end_time,
            setup_buffer_minutes=setup_buffer,
            teardown_buffer_minutes=teardown_buffer,
            exclude_event_id=int(exclude_event_id) if exclude_event_id else None,
        )

        return jsonify({
            "is_sufficient": is_sufficient,
            "item_statuses": item_statuses,
            "shortages": shortages,
        }), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@event_bp.route("/<int:event_id>/confirm", methods=["POST"])
@organizer_or_admin_required
def confirm_booking(event_id: int):
    """
    Confirms an event booking inside an atomic database transaction.
    Re-evaluates live availability after acquiring pessimistic locks.
    """
    user = get_current_user()
    event, error = get_event_by_id(db_session, event_id, user=user)
    if error:
        status_code = 403 if "Forbidden" in error else 404
        return jsonify({"error": error}), status_code

    data = request.get_json(silent=True) or {}
    idempotency_key = data.get("idempotency_key") or request.headers.get("Idempotency-Key")

    confirmed_event, failure = confirm_event_booking(
        db=db_session,
        event_id=event_id,
        user_id=user.id,
        idempotency_key=idempotency_key,
    )
    if failure:
        return jsonify(failure), 409  # Conflict status code for booking shortage/conflict

    return jsonify({
        "message": f"Event '{confirmed_event.name}' confirmed successfully.",
        "event": confirmed_event.to_dict(include_items=True)
    }), 200


@event_bp.route("/<int:event_id>/cancel", methods=["POST"])
@organizer_or_admin_required
def cancel_booking(event_id: int):
    """Cancels an event and immediately releases allocated stock."""
    user = get_current_user()
    event, error = get_event_by_id(db_session, event_id, user=user)
    if error:
        status_code = 403 if "Forbidden" in error else 404
        return jsonify({"error": error}), status_code

    cancelled_event, err = cancel_event_booking(
        db=db_session,
        event_id=event_id,
        user_id=user.id,
    )
    if err:
        return jsonify({"error": err}), 400

    return jsonify({
        "message": f"Event '{cancelled_event.name}' has been cancelled.",
        "event": cancelled_event.to_dict(include_items=True)
    }), 200


@event_bp.route("/<int:event_id>", methods=["PUT"])
@organizer_or_admin_required
def edit_or_reschedule_event(event_id: int):
    """
    Reschedules or edits an event. Re-checks availability if already confirmed.
    """
    user = get_current_user()
    event, error = get_event_by_id(db_session, event_id, user=user)
    if error:
        status_code = 403 if "Forbidden" in error else 404
        return jsonify({"error": error}), status_code

    data = request.get_json(silent=True) or {}
    updated_event, failure = reschedule_or_edit_event(
        db=db_session,
        event_id=event_id,
        data=data,
        user_id=user.id,
    )
    if failure:
        return jsonify(failure), 409 if "Insufficient" in failure.get("error", "") else 400

    return jsonify({
        "message": f"Event '{updated_event.name}' updated successfully.",
        "event": updated_event.to_dict(include_items=True)
    }), 200


@event_bp.route("/<int:event_id>/complete", methods=["POST"])
@organizer_or_admin_required
def mark_event_completed(event_id: int):
    """
    Marks event as completed.
    Consumables are permanently deducted from total stock; returnables are released.
    """
    user = get_current_user()
    event, error = get_event_by_id(db_session, event_id, user=user)
    if error:
        status_code = 403 if "Forbidden" in error else 404
        return jsonify({"error": error}), status_code

    completed_event, err = complete_event(
        db=db_session,
        event_id=event_id,
        user_id=user.id,
    )
    if err:
        return jsonify({"error": err}), 400

    return jsonify({
        "message": f"Event '{completed_event.name}' marked completed.",
        "event": completed_event.to_dict(include_items=True)
    }), 200
