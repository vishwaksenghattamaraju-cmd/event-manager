import csv
import io
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, Response
from sqlalchemy import func
from backend.models.base import db_session
from backend.models.inventory import InventoryItem
from backend.models.event import Event, EventStatus
from backend.models.user import User
from backend.routes.auth_routes import organizer_or_admin_required, get_current_user

report_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@report_bp.route("/dashboard-summary", methods=["GET"])
@organizer_or_admin_required
def get_dashboard_summary():
    """
    Returns live statistics computed directly from database tables.
    CRITICAL: Never uses hardcoded or cached values.
    """
    user = get_current_user()
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. Inventory stats
    active_items = db_session.query(InventoryItem).filter(InventoryItem.is_active.is_(True)).all()
    total_active_items_count = len(active_items)
    total_physical_stock = sum(item.total_stock for item in active_items)
    total_unavailable_stock = sum(item.unavailable_stock for item in active_items)

    # Items at risk: (total - unavailable) <= minimum_threshold
    items_at_risk = [
        item.to_dict()
        for item in active_items
        if (item.total_stock - item.unavailable_stock) <= item.minimum_threshold
    ]

    # Category breakdown for Chart.js
    category_counts = {}
    for item in active_items:
        category_counts[item.category] = category_counts.get(item.category, 0) + item.total_stock

    # 2. Event stats (filtered by role: organizer sees own, admin sees all)
    event_query = db_session.query(Event)
    if not user.is_admin:
        event_query = event_query.filter(Event.organizer_id == user.id)

    total_events_count = event_query.count()

    upcoming_confirmed_events_count = (
        event_query
        .filter(Event.status == EventStatus.CONFIRMED, Event.end_time >= now_utc)
        .count()
    )

    # Recent bookings (up to 5 most recent)
    recent_events = (
        event_query
        .order_by(Event.created_at.desc())
        .limit(6)
        .all()
    )

    return jsonify({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "inventory": {
            "total_items_count": total_active_items_count,
            "total_physical_stock": total_physical_stock,
            "total_unavailable_stock": total_unavailable_stock,
            "items_at_risk_count": len(items_at_risk),
            "items_at_risk": items_at_risk,
            "category_distribution": [
                {"category": cat, "total_stock": qty}
                for cat, qty in category_counts.items()
            ],
        },
        "events": {
            "total_events_count": total_events_count,
            "upcoming_confirmed_count": upcoming_confirmed_events_count,
            "recent_events": [e.to_dict(include_items=True) for e in recent_events],
        },
    }), 200


@report_bp.route("/inventory-csv", methods=["GET"])
@organizer_or_admin_required
def export_inventory_csv():
    """
    Exports full live inventory catalog as a CSV download.
    Includes SKU, name, category, item_type, stock counts, and costs.
    """
    items = (
        db_session.query(InventoryItem)
        .filter(InventoryItem.is_active.is_(True))
        .order_by(InventoryItem.category.asc(), InventoryItem.name.asc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # Headers
    writer.writerow([
        "Item ID",
        "SKU",
        "Item Name",
        "Category",
        "Item Type",
        "Total Stock",
        "Unavailable Stock",
        "Net Available Stock",
        "Minimum Safety Threshold",
        "Unit",
        "Unit Cost ($)",
        "Stock Status",
    ])

    for item in items:
        net = item.physically_available_base
        if net == 0:
            status = "OUT OF STOCK"
        elif net <= item.minimum_threshold:
            status = "LOW STOCK"
        else:
            status = "HEALTHY"

        writer.writerow([
            item.id,
            item.sku,
            item.name,
            item.category,
            item.item_type,
            item.total_stock,
            item.unavailable_stock,
            net,
            item.minimum_threshold,
            item.unit,
            f"{item.purchase_cost:.2f}",
            status,
        ])

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"inventory_report_{timestamp}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
        },
    )


@report_bp.route("/event-summary-csv", methods=["GET"])
@organizer_or_admin_required
def export_events_summary_csv():
    """
    Exports summary of events within an optional date range as a CSV download.
    Admins see all events; Organizers see their own events.
    Query parameters:
      - start_date (YYYY-MM-DD or ISO string)
      - end_date (YYYY-MM-DD or ISO string)
      - status (draft, confirmed, cancelled, completed)
    """
    user = get_current_user()
    query = db_session.query(Event)

    if not user.is_admin:
        query = query.filter(Event.organizer_id == user.id)

    status_param = request.args.get("status")
    if status_param:
        query = query.filter(Event.status == status_param.strip().lower())

    start_date_str = request.args.get("start_date")
    if start_date_str:
        try:
            clean_s = start_date_str.replace("Z", "").split("T")[0]
            start_dt = datetime.strptime(clean_s, "%Y-%m-%d")
            query = query.filter(Event.start_time >= start_dt)
        except ValueError:
            pass

    end_date_str = request.args.get("end_date")
    if end_date_str:
        try:
            clean_e = end_date_str.replace("Z", "").split("T")[0]
            end_dt = datetime.strptime(clean_e, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.filter(Event.end_time <= end_dt)
        except ValueError:
            pass

    events = query.order_by(Event.start_time.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Event ID",
        "Event Name",
        "Event Type",
        "Status",
        "Start Time (UTC)",
        "End Time (UTC)",
        "Expected Attendees",
        "Location",
        "Organizer",
        "Reserved Items Summary",
        "Created At",
    ])

    for ev in events:
        items_summary_parts = []
        for ei in ev.items:
            item_name = ei.item.name if ei.item else f"Item #{ei.item_id}"
            items_summary_parts.append(f"{item_name} (x{ei.quantity})")
        items_summary = "; ".join(items_summary_parts) if items_summary_parts else "None"

        organizer_name = ev.organizer.username if ev.organizer else f"User #{ev.organizer_id}"

        writer.writerow([
            ev.id,
            ev.name,
            ev.event_type or "standard",
            ev.status.upper(),
            ev.start_time.strftime("%Y-%m-%d %H:%M UTC") if ev.start_time else "",
            ev.end_time.strftime("%Y-%m-%d %H:%M UTC") if ev.end_time else "",
            ev.expected_guest_count,
            ev.location or "N/A",
            organizer_name,
            items_summary,
            ev.created_at.strftime("%Y-%m-%d %H:%M UTC") if ev.created_at else "",
        ])

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"events_summary_{timestamp}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
        },
    )
