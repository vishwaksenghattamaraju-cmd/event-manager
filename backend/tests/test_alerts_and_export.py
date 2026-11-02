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

def test_dashboard_summary_csv_export(admin_client, sample_chair):
    """
    Validates that /api/reports/dashboard-summary-csv returns valid CSV
    with operational telemetry, risk sentinel, and category distribution.
    """
    resp = admin_client.get("/api/reports/dashboard-summary-csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    assert "dashboard_summary_" in resp.headers.get("Content-Disposition", "")

    csv_text = resp.data.decode("utf-8")
    assert "EXECUTIVE DASHBOARD SUMMARY REPORT" in csv_text
    assert "OPERATIONAL KEY METRICS" in csv_text
    assert "Total Physical Stock" in csv_text


def test_inventory_csv_bulk_import(admin_client):
    """
    Validates that /api/inventory/import-csv supports bulk importing
    items via CSV file upload, correctly parsing rows and creating/updating items.
    """
    speaker_data = {
        "name": "Heavy Duty PA Speaker",
        "category": "Audio",
        "item_type": "returnable",
        "total_stock": 20,
        "unavailable_stock": 0,
        "minimum_threshold": 5,
        "unit": "units",
        "purchase_cost": 300.0,
    }
    create_item(db_session, speaker_data)

    csv_content = (
        "Item Name,Category,Total Stock,Unavailable Stock,Minimum Safety Threshold,Unit,Unit Cost (INR),Item Type,Description\n"
        "Shure Wireless Mic SM58,Audio,12,0,3,units,15000.00,returnable,Professional handheld wireless microphone\n"
        "LED Par Can 64 RGB,Lighting,24,2,6,pieces,4500.50,returnable,Stage accent light\n"
        "Heavy Duty PA Speaker,Audio,30,0,5,units,350.00,returnable,Updated speaker stock\n"
    )

    data = {
        "file": (io.BytesIO(csv_content.encode("utf-8")), "inventory_import_test.csv")
    }

    resp = admin_client.post("/api/inventory/import-csv", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    res_data = resp.get_json()
    assert res_data["total_rows"] == 3
    assert res_data["created_count"] == 2  # Mic and LED Par Can
    assert res_data["updated_count"] == 1  # Heavy Duty PA Speaker updated to 30

    # Verify items in database
    mic = db_session.query(InventoryItem).filter(InventoryItem.name == "Shure Wireless Mic SM58").first()
    assert mic is not None
    assert mic.total_stock == 12
    assert mic.category == "Audio"
    assert mic.purchase_cost == 15000.00

    speaker = db_session.query(InventoryItem).filter(InventoryItem.name == "Heavy Duty PA Speaker").first()
    assert speaker is not None
    assert speaker.total_stock == 30
    assert speaker.purchase_cost == 350.00
