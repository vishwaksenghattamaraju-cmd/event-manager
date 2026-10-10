"""Tests for Inventory CRUD, soft-delete rules, and immutable transaction history."""

import pytest
from backend.models.base import db_session
from backend.models.inventory import InventoryItem, InventoryTransaction


def test_inventory_item_creation_and_update(admin_client):
    """Test 5 (Part 1): Inventory item can be created and updated."""
    # 1. Create item
    create_resp = admin_client.post(
        "/api/inventory",
        json={
            "name": "Round Dining Table",
            "category": "Tables",
            "description": "60-inch round wooden table",
            "item_type": "returnable",
            "total_stock": 20,
            "unavailable_stock": 0,
            "minimum_threshold": 4,
            "unit": "pieces",
            "purchase_cost": 85.0,
        },
    )
    assert create_resp.status_code == 201
    created_item = create_resp.get_json()["item"]
    item_id = created_item["id"]
    assert created_item["name"] == "Round Dining Table"
    assert created_item["total_stock"] == 20
    assert created_item["is_active"] is True

    # Verify initial transaction history
    tx_resp = admin_client.get(f"/api/inventory/{item_id}/transactions")
    assert tx_resp.status_code == 200
    tx_data = tx_resp.get_json()["transactions"]
    assert len(tx_data) == 1
    assert tx_data[0]["transaction_type"] == "initial"
    assert tx_data[0]["new_total_stock"] == 20

    # 2. Update item (change stock from 20 to 25)
    update_resp = admin_client.put(
        f"/api/inventory/{item_id}",
        json={
            "total_stock": 25,
            "description": "Updated description",
            "reason": "Purchased 5 additional tables",
        },
    )
    assert update_resp.status_code == 200
    updated_item = update_resp.get_json()["item"]
    assert updated_item["total_stock"] == 25
    assert updated_item["description"] == "Updated description"

    # Verify second transaction was appended
    tx_resp2 = admin_client.get(f"/api/inventory/{item_id}/transactions")
    assert tx_resp2.status_code == 200
    tx_data2 = tx_resp2.get_json()["transactions"]
    assert len(tx_data2) == 2
    assert tx_data2[0]["transaction_type"] == "stock_in"
    assert tx_data2[0]["change_amount"] == 5
    assert tx_data2[0]["new_total_stock"] == 25


def test_deactivated_item_with_history_is_not_deleted(admin_client, sample_chair):
    """Test 5 (Part 2): Deactivated item with history is soft-deleted, never removed from database."""
    item_id = sample_chair.id

    # Deactivate (soft delete)
    delete_resp = admin_client.delete(f"/api/inventory/{item_id}")
    assert delete_resp.status_code == 200
    data = delete_resp.get_json()
    assert data["item"]["is_active"] is False

    # Verify directly from database: row STILL exists!
    item_in_db = db_session.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    assert item_in_db is not None
    assert item_in_db.is_active is False

    # Verify transactions are preserved
    tx_in_db = (
        db_session.query(InventoryTransaction)
        .filter(InventoryTransaction.item_id == item_id)
        .all()
    )
    assert len(tx_in_db) >= 2  # initial + deactivation transaction


def test_stock_never_goes_negative(admin_client, sample_chair):
    """Test 15: Stock cannot go below zero via creation, update, or adjustment."""
    # 1. Attempt to create item with negative stock
    resp1 = admin_client.post(
        "/api/inventory",
        json={"name": "Faulty Item", "category": "Decor", "total_stock": -5},
    )
    assert resp1.status_code == 400
    assert "negative" in resp1.get_json()["error"].lower()

    # 2. Attempt to update item total_stock to negative
    resp2 = admin_client.put(
        f"/api/inventory/{sample_chair.id}",
        json={"total_stock": -10},
    )
    assert resp2.status_code == 400
    assert "negative" in resp2.get_json()["error"].lower()

    # 3. Attempt to adjust stock below zero
    # sample_chair has 100 in stock; deducting 150 must be rejected
    resp3 = admin_client.post(
        f"/api/inventory/{sample_chair.id}/adjust",
        json={"change_amount": -150, "reason": "Accidental massive deduction"},
    )
    assert resp3.status_code == 400
    assert "negative" in resp3.get_json()["error"].lower()

    # Verify stock remained untouched at 100
    resp_check = admin_client.get(f"/api/inventory/{sample_chair.id}")
    assert resp_check.get_json()["item"]["total_stock"] == 100


def test_unavailable_stock_validation(admin_client, sample_chair):
    """Ensure unavailable (damaged/maintenance) stock cannot exceed total stock."""
    # sample_chair has total_stock = 100
    # Trying to mark 150 as damaged should be rejected
    resp = admin_client.post(
        f"/api/inventory/{sample_chair.id}/unavailable",
        json={"amount": 150, "reason": "Severe flood damage"},
    )
    assert resp.status_code == 400
    assert "exceed" in resp.get_json()["error"].lower()

    # Marking 10 as damaged should succeed
    resp_valid = admin_client.post(
        f"/api/inventory/{sample_chair.id}/unavailable",
        json={"amount": 10, "reason": "Broken chair legs"},
    )
    assert resp_valid.status_code == 200
    item = resp_valid.get_json()["item"]
    assert item["unavailable_stock"] == 10
    assert item["physically_available_base"] == 90  # 100 - 10


def test_organizer_visibility_rules(organizer_client, admin_client, sample_chair):
    """Organizers see active inventory, but cannot see deactivated items."""
    item_id = sample_chair.id

    # Active item is visible to organizer
    resp1 = organizer_client.get(f"/api/inventory/{item_id}")
    assert resp1.status_code == 200

    # Admin deactivates item
    del_resp = admin_client.delete(f"/api/inventory/{item_id}")
    assert del_resp.status_code == 200

    # Organizer now gets 404
    resp2 = organizer_client.get(f"/api/inventory/{item_id}")
    assert resp2.status_code == 404

    # Admin can still view deactivated item
    admin_resp = admin_client.get(f"/api/inventory/{item_id}")
    assert admin_resp.status_code == 200
    assert admin_resp.get_json()["item"]["is_active"] is False


def test_delete_inventory_item_permanent(admin_client):
    """Test permanently deleting an unbooked item."""
    create_resp = admin_client.post(
        "/api/inventory",
        json={"name": "Temporary Banner", "category": "Decor", "total_stock": 5},
    )
    assert create_resp.status_code == 201
    item_id = create_resp.get_json()["item"]["id"]

    # Permanent delete
    del_resp = admin_client.delete(f"/api/inventory/{item_id}?permanent=true")
    assert del_resp.status_code == 200

    # Item is completely gone
    get_resp = admin_client.get(f"/api/inventory/{item_id}")
    assert get_resp.status_code == 404


def test_role_toggle_workflow(organizer_client):
    """Test toggling role between organizer and admin."""
    # Initially organizer cannot add item
    res1 = organizer_client.post("/api/inventory", json={"name": "VIP Booth", "category": "Decor"})
    assert res1.status_code == 403

    # Toggle role to admin
    toggle_resp = organizer_client.post("/api/auth/toggle-role")
    assert toggle_resp.status_code == 200
    assert toggle_resp.get_json()["role"] == "admin"
    assert toggle_resp.get_json()["is_admin"] is True

    # Now can add item
    res2 = organizer_client.post("/api/inventory", json={"name": "VIP Booth", "category": "Decor", "total_stock": 10})
    assert res2.status_code == 201

