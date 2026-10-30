"""
Automated tests for Phase 6: Advanced Features (CSV Export + Alert Engine).

Covers:
- Test #22: Low-stock alert generated when threshold breached; resolving alert sets is_resolved=True.
- Test #23: CSV export returns valid format, correct headers, and data rows.
- Test #24: High shortage risk alert generated from ML risk assessment.
"""

import csv
import io
from datetime import datetime, timezone, timedelta
import pytest
from backend.models.base import db_session
from backend.models.inventory import InventoryItem, ItemType
from backend.models.event import Event, EventItem, EventStatus, EventType
from backend.models.alert import Alert, AlertType, AlertSeverity
from backend.services.inventory_service import create_item, adjust_stock
from backend.services.alert_service import (
    check_and_create_stock_alert,
    create_ml_shortage_risk_alert,
    get_active_alerts,
    resolve_alert,
)


def test_test22_low_stock_alert_generated_and_resolved(admin_client):
    """
    Test #22:
    - Low-stock alert generated when inventory breaches minimum safety threshold.
    - Resolving alert sets is_resolved=True (and records reviewed_at timestamp).
    - Stock replenishing above threshold auto-resolves active stock alerts.
    """
    # 1. Create an inventory item with 20 units and threshold of 5
    item_data = {
        "name": "Heavy Duty PA Speaker",
        "category": "Audio",
        "item_type": "returnable",
        "total_stock": 20,
        "unavailable_stock": 0,
        "minimum_threshold": 5,
        "unit": "units",
        "purchase_cost": 350.0,
    }
    item, err = create_item(db_session, item_data)
    assert err is None
    assert item is not None

    # Stock is 20 > 5, no alert should exist
    alerts = get_active_alerts(db_session)
    assert len([a for a in alerts if a.item_id == item.id]) == 0

    # 2. Adjust stock down by -16 -> leaves 4 available (which is <= threshold 5)
    adjusted_item, adj_err = adjust_stock(db_session, item.id, -16, "Sent units to secondary warehouse")
    assert adj_err is None
    assert adjusted_item.total_stock == 4

    # 3. Verify that a LOW_STOCK alert was generated automatically
    active_alerts = get_active_alerts(db_session)
    matching_alerts = [a for a in active_alerts if a.item_id == item.id]
    assert len(matching_alerts) >= 1
    low_alert = matching_alerts[0]
    assert low_alert.alert_type == AlertType.LOW_STOCK
    assert low_alert.severity == AlertSeverity.WARNING
    assert low_alert.is_resolved is False

    # 4. Resolve the alert via HTTP endpoint
    resp = admin_client.post(f"/api/alerts/{low_alert.id}/resolve")
    assert resp.status_code == 200, f"Resolve endpoint failed: {resp.get_json()}"
    resolve_data = resp.get_json()
    assert resolve_data["alert"]["is_resolved"] is True
    assert resolve_data["alert"]["reviewed_at"] is not None

    # Verify directly in database
    db_alert = db_session.query(Alert).filter(Alert.id == low_alert.id).first()
    assert db_alert.is_resolved is True
    assert db_alert.resolved_at is not None

    # 5. Out of stock alert test: adjust by -4 -> leaves 0
    adj2_item, adj2_err = adjust_stock(db_session, item.id, -4, "All remaining units allocated")
    assert adj2_err is None
    assert adj2_item.total_stock == 0

    active_alerts_out = get_active_alerts(db_session)
    out_alerts = [a for a in active_alerts_out if a.item_id == item.id and a.alert_type == AlertType.OUT_OF_STOCK]
    assert len(out_alerts) == 1
    assert out_alerts[0].severity == AlertSeverity.CRITICAL

    # 6. Auto-resolution: Replenish stock to 15 (> threshold 5)
    adj3_item, adj3_err = adjust_stock(db_session, item.id, 15, "New procurement batch arrived")
    assert adj3_err is None
    assert adj3_item.total_stock == 15

    # Any stock alerts for this item should now be automatically resolved
    active_post_restock = get_active_alerts(db_session)
    item_alerts_post = [a for a in active_post_restock if a.item_id == item.id]
    assert len(item_alerts_post) == 0


def test_test23_csv_export_inventory_and_events(admin_client, organizer_user):
    """
    Test #23:
    - Inventory CSV export returns valid format, proper headers, and accurate stock numbers.
    - Event summary CSV export returns valid format and proper metadata headers.
    """
    # 1. Seed two items
    item1_data = {
        "name": "Standard Folding Chair",
        "category": "Furniture",
        "item_type": "returnable",
        "total_stock": 100,
        "unavailable_stock": 5,
        "minimum_threshold": 20,
        "unit": "chairs",
        "purchase_cost": 25.0,
    }
    item1, _ = create_item(db_session, item1_data)

    item2_data = {
        "name": "Biodegradable Party Confetti",
        "category": "Decorations",
        "item_type": "consumable",
        "total_stock": 50,
        "unavailable_stock": 0,
        "minimum_threshold": 10,
        "unit": "packs",
        "purchase_cost": 4.5,
    }
    item2, _ = create_item(db_session, item2_data)

    # 2. Test Inventory CSV Export
    resp_inv = admin_client.get("/api/reports/inventory-csv")
    assert resp_inv.status_code == 200
    assert "text/csv" in resp_inv.content_type
    assert "attachment" in resp_inv.headers.get("Content-Disposition", "")
    assert "inventory_report_" in resp_inv.headers.get("Content-Disposition", "")

    csv_text = resp_inv.data.decode("utf-8")
    csv_file = io.StringIO(csv_text)
    reader = csv.reader(csv_file)
    rows = list(reader)

    assert len(rows) >= 3  # Header + 2 items
    headers = rows[0]
    expected_headers = [
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
    ]
    assert headers == expected_headers

    item_names_in_csv = [row[2] for row in rows[1:]]
    assert "Standard Folding Chair" in item_names_in_csv
    assert "Biodegradable Party Confetti" in item_names_in_csv

    # Check chair row details: total=100, unavail=5, net=95
    chair_row = next(r for r in rows[1:] if r[2] == "Standard Folding Chair")
    assert chair_row[5] == "100"
    assert chair_row[6] == "5"
    assert chair_row[7] == "95"
    assert chair_row[11] == "HEALTHY"

    # 3. Seed an Event
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ev = Event(
        name="Annual Tech Gala",
        event_type=EventType.CONFERENCE,
        status=EventStatus.CONFIRMED,
        start_time=now + timedelta(days=2),
        end_time=now + timedelta(days=2, hours=6),
        expected_guest_count=120,
        location="Grand Ballroom A",
        organizer_id=organizer_user.id,
    )
    db_session.add(ev)
    db_session.flush()

    ev_item = EventItem(event_id=ev.id, item_id=item1.id, quantity=80)
    db_session.add(ev_item)
    db_session.commit()

    # 4. Test Event Summary CSV Export
    resp_ev = admin_client.get("/api/reports/event-summary-csv")
    assert resp_ev.status_code == 200
    assert "text/csv" in resp_ev.content_type
    assert "attachment" in resp_ev.headers.get("Content-Disposition", "")
    assert "events_summary_" in resp_ev.headers.get("Content-Disposition", "")

    ev_csv_text = resp_ev.data.decode("utf-8")
    ev_csv_file = io.StringIO(ev_csv_text)
    ev_reader = csv.reader(ev_csv_file)
    ev_rows = list(ev_reader)

    assert len(ev_rows) >= 2  # Header + Gala event
    ev_headers = ev_rows[0]
    expected_ev_headers = [
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
    ]
    assert ev_headers == expected_ev_headers

    gala_row = next(r for r in ev_rows[1:] if r[1] == "Annual Tech Gala")
    assert gala_row[2] == "conference"
    assert gala_row[3] == "CONFIRMED"
    assert gala_row[6] == "120"
    assert gala_row[7] == "Grand Ballroom A"
    assert "Standard Folding Chair (x80)" in gala_row[9]


def test_test24_high_shortage_risk_alert_from_ml(admin_client, organizer_client):
    """
    Test #24:
    - High shortage risk alert generated from ML risk assessment.
    - Returned in active alerts list with CRITICAL severity.
    - Successfully resolved via resolution endpoint.
    """
    # 1. Create catalog item
    item_data = {
        "name": "4K Projector Pro",
        "category": "Video",
        "item_type": "returnable",
        "total_stock": 5,
        "unavailable_stock": 0,
        "minimum_threshold": 2,
        "unit": "units",
        "purchase_cost": 1200.0,
    }
    item, _ = create_item(db_session, item_data)

    # 2. Generate ML shortage risk alert
    ml_alert = create_ml_shortage_risk_alert(
        db=db_session,
        item_id=item.id,
        risk_score=0.92,
        risk_level="High",
        reason="Upcoming weekend commitments require 6 units but only 5 are physically stocked.",
    )
    assert ml_alert is not None
    assert ml_alert.alert_type == AlertType.HIGH_SHORTAGE_RISK
    assert ml_alert.severity == AlertSeverity.CRITICAL
    assert ml_alert.is_resolved is False

    # 3. Retrieve active alerts via GET /api/alerts
    resp = organizer_client.get("/api/alerts")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_active"] >= 1
    assert data["critical_count"] >= 1

    matching = [a for a in data["alerts"] if a["id"] == ml_alert.id]
    assert len(matching) == 1
    alert_dict = matching[0]
    assert alert_dict["alert_type"] == "high_shortage_risk"
    assert alert_dict["severity"] == "CRITICAL"
    assert "High Shortage Risk (92%)" in alert_dict["message"]

    # 4. Resolve the ML alert
    resolve_resp = admin_client.post(f"/api/alerts/{ml_alert.id}/resolve")
    assert resolve_resp.status_code == 200
    resolve_data = resolve_resp.get_json()
    assert resolve_data["alert"]["is_resolved"] is True

    # 5. Verify it no longer appears in active alerts
    resp_after = organizer_client.get("/api/alerts")
    data_after = resp_after.get_json()
    assert ml_alert.id not in [a["id"] for a in data_after["alerts"]]
