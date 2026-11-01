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


@report_bp.route("/dashboard-summary-csv", methods=["GET"])
@organizer_or_admin_required
def export_dashboard_summary_csv():
    """
    Exports comprehensive executive dashboard summary as CSV download.
    Includes:
      - High-level KPIs (Total Items, Physical Stock, Unavailable, Net Available, Risk Items, Active Bookings)
      - Category distribution
      - Sentinel items currently at shortage risk
      - Upcoming confirmed bookings
    """
    user = get_current_user()
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    active_items = db_session.query(InventoryItem).filter(InventoryItem.is_active.is_(True)).all()
    total_physical_stock = sum(item.total_stock for item in active_items)
    total_unavailable_stock = sum(item.unavailable_stock for item in active_items)
    net_usable = total_physical_stock - total_unavailable_stock

    items_at_risk = [
        item for item in active_items
        if (item.total_stock - item.unavailable_stock) <= item.minimum_threshold
    ]

    event_query = db_session.query(Event)
    if not user.is_admin:
        event_query = event_query.filter(Event.organizer_id == user.id)

    total_events = event_query.count()
    upcoming_events = (
        event_query
        .filter(Event.status == EventStatus.CONFIRMED, Event.end_time >= now_utc)
        .order_by(Event.start_time.asc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # 1. Title & Header
    writer.writerow(["EXECUTIVE DASHBOARD SUMMARY REPORT"])
    writer.writerow(["Generated At (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow(["Requested By", f"{user.username} ({user.role.upper()})"])
    writer.writerow([])

    # 2. Key Operational Telemetry
    writer.writerow(["--- OPERATIONAL KEY METRICS ---"])
    writer.writerow(["Metric", "Value", "Description"])
    writer.writerow(["Total Trackable SKUs", len(active_items), "Active item types across all zones"])
    writer.writerow(["Total Physical Stock (Units)", total_physical_stock, "Total units recorded in warehouse"])
    writer.writerow(["Unavailable / Damaged Stock", total_unavailable_stock, "Units currently damaged, lost or in maintenance"])
    writer.writerow(["Net Usable Stock (Units)", net_usable, "Physically available for allocation"])
    writer.writerow(["Shortage Sentinel Alerts", len(items_at_risk), "Items at or below safety threshold"])
    writer.writerow(["Total Registered Events", total_events, "All historical and active events"])
    writer.writerow(["Upcoming Confirmed Bookings", len(upcoming_events), "Upcoming bookings requiring gear"])
    writer.writerow([])

    # 3. Category Breakdown
    cat_counts = {}
    for it in active_items:
        cat_counts[it.category] = cat_counts.get(it.category, 0) + it.total_stock
    writer.writerow(["--- INVENTORY BY CATEGORY ---"])
    writer.writerow(["Category", "Total Units"])
    for cat, count in sorted(cat_counts.items()):
        writer.writerow([cat, count])
    writer.writerow([])

    # 4. Items at Shortage Risk
    writer.writerow(["--- SHORTAGE SENTINEL: ITEMS AT RISK ---"])
    writer.writerow(["Item ID", "SKU", "Item Name", "Category", "Total Stock", "Unavailable", "Net Available", "Safety Threshold", "Unit", "Stock Status"])
    if items_at_risk:
        for it in items_at_risk:
            net = it.total_stock - it.unavailable_stock
            status = "OUT OF STOCK" if net == 0 else "LOW STOCK"
            writer.writerow([it.id, it.sku, it.name, it.category, it.total_stock, it.unavailable_stock, net, it.minimum_threshold, it.unit, status])
    else:
        writer.writerow(["None", "-", "All items are within healthy operating thresholds", "-", "-", "-", "-", "-", "-", "HEALTHY"])
    writer.writerow([])

    # 5. Upcoming Bookings
    writer.writerow(["--- UPCOMING CONFIRMED BOOKINGS ---"])
    writer.writerow(["Event ID", "Event Name", "Start Time (UTC)", "End Time (UTC)", "Location", "Expected Attendees", "Organizer"])
    if upcoming_events:
        for ev in upcoming_events:
            org = ev.organizer.username if ev.organizer else f"User #{ev.organizer_id}"
            writer.writerow([
                ev.id,
                ev.name,
                ev.start_time.strftime("%Y-%m-%d %H:%M UTC") if ev.start_time else "",
                ev.end_time.strftime("%Y-%m-%d %H:%M UTC") if ev.end_time else "",
                ev.location or "N/A",
                ev.expected_guest_count,
                org
            ])
    else:
        writer.writerow(["None", "No upcoming confirmed bookings scheduled", "-", "-", "-", "-", "-"])

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"dashboard_summary_{timestamp}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
        },
    )


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
        "Unit Cost (INR)",
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
