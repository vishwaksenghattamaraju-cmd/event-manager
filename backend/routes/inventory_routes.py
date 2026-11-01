"""Inventory routes: CRUD, stock adjustment, and transaction history endpoints."""

import csv
import io
import re
from flask import Blueprint, request, jsonify
from backend.models.base import db_session
from backend.models.inventory import InventoryItem, InventoryTransaction, TransactionType, ItemType
from backend.services.alert_service import check_and_create_stock_alert
from backend.routes.auth_routes import login_required, admin_required, organizer_or_admin_required, get_current_user
from backend.services.inventory_service import (
    get_all_items,
    get_item_by_id,
    create_item,
    update_item,
    adjust_stock,
    mark_stock_unavailable,
    deactivate_item,
    get_item_transactions,
)

inventory_bp = Blueprint("inventory", __name__, url_prefix="/api/inventory")


@inventory_bp.route("", methods=["GET"])
@inventory_bp.route("/items", methods=["GET"])
@organizer_or_admin_required
def list_inventory():
    """
    Lists inventory items.
    Organizers see only active items.
    Admins can see inactive items by passing ?include_inactive=true.
    """
    user = get_current_user()
    include_inactive = False
    if user.is_admin and request.args.get("include_inactive", "").lower() == "true":
        include_inactive = True

    category = request.args.get("category")
    search = request.args.get("search")

    items = get_all_items(
        db_session,
        include_inactive=include_inactive,
        category=category,
        search=search
    )
    return jsonify({
        "items": [item.to_dict() for item in items],
        "count": len(items)
    }), 200


@inventory_bp.route("/<int:item_id>", methods=["GET"])
@inventory_bp.route("/items/<int:item_id>", methods=["GET"])
@organizer_or_admin_required
def get_inventory_item(item_id: int):
    """Retrieves single inventory item details."""
    item = get_item_by_id(db_session, item_id)
    if not item:
        return jsonify({"error": "Inventory item not found."}), 404

    user = get_current_user()
    if not item.is_active and not user.is_admin:
        return jsonify({"error": "Inventory item not found or deactivated."}), 404

    return jsonify({"item": item.to_dict()}), 200


@inventory_bp.route("", methods=["POST"])
@inventory_bp.route("/items", methods=["POST"])
@admin_required
def add_inventory_item():
    """Creates a new inventory item (Admin only)."""
    data = request.get_json() or {}
    user = get_current_user()

    item, error = create_item(db_session, data, user_id=user.id)
    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Inventory item created successfully.",
        "item": item.to_dict()
    }), 201


@inventory_bp.route("/<int:item_id>", methods=["PUT"])
@admin_required
def edit_inventory_item(item_id: int):
    """Updates an existing inventory item (Admin only)."""
    data = request.get_json() or {}
    user = get_current_user()

    item, error = update_item(db_session, item_id, data, user_id=user.id)
    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Inventory item updated successfully.",
        "item": item.to_dict()
    }), 200


@inventory_bp.route("/<int:item_id>/adjust", methods=["POST"])
@admin_required
def adjust_inventory_stock(item_id: int):
    """Adjusts physical stock quantity by an amount with a reason (Admin only)."""
    data = request.get_json() or {}
    user = get_current_user()

    change_amount = data.get("change_amount")
    reason = data.get("reason", "")

    if change_amount is None:
        return jsonify({"error": "Field 'change_amount' is required."}), 400

    try:
        change_amount = int(change_amount)
    except ValueError:
        return jsonify({"error": "Field 'change_amount' must be an integer."}), 400

    item, error = adjust_stock(
        db_session,
        item_id=item_id,
        change_amount=change_amount,
        reason=reason,
        user_id=user.id
    )
    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": "Stock adjusted successfully.",
        "item": item.to_dict()
    }), 200


@inventory_bp.route("/<int:item_id>/unavailable", methods=["POST"])
@admin_required
def set_unavailable_stock(item_id: int):
    """Marks items as damaged or in maintenance (Admin only)."""
    data = request.get_json() or {}
    user = get_current_user()

    amount = data.get("amount")
    reason = data.get("reason", "")
    status_kind = data.get("status_kind", "damaged")

    if amount is None or int(amount) < 0:
        return jsonify({"error": "Positive integer 'amount' is required."}), 400

    item, error = mark_stock_unavailable(
        db_session,
        item_id=item_id,
        amount=int(amount),
        reason=reason,
        user_id=user.id,
        status_kind=status_kind
    )
    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": f"Updated unavailable stock ({status_kind}).",
        "item": item.to_dict()
    }), 200


@inventory_bp.route("/<int:item_id>", methods=["DELETE"])
@admin_required
def soft_delete_inventory_item(item_id: int):
    """Deactivates an inventory item (Soft delete, Admin only)."""
    user = get_current_user()
    permanent = request.args.get("permanent", "").lower() == "true"

    if permanent:
        from backend.models.event import EventItem
        has_bookings = db_session.query(EventItem).filter(EventItem.item_id == item_id).first()
        if not has_bookings:
            item = get_item_by_id(db_session, item_id)
            if not item:
                return jsonify({"error": "Inventory item not found."}), 404
            name = item.name
            db_session.delete(item)
            db_session.commit()
            return jsonify({
                "message": f"Item '{name}' permanently deleted.",
                "item": {"id": item_id, "name": name, "is_active": False}
            }), 200

    item, error = deactivate_item(db_session, item_id, user_id=user.id)
    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "message": f"Item '{item.name}' has been deleted from inventory.",
        "item": item.to_dict()
    }), 200



@inventory_bp.route("/<int:item_id>/transactions", methods=["GET"])
@admin_required
def list_item_transactions(item_id: int):
    """Returns the immutable audit history for an item (Admin only)."""
    item = get_item_by_id(db_session, item_id)
    if not item:
        return jsonify({"error": "Inventory item not found."}), 404

    transactions = get_item_transactions(db_session, item_id)
    return jsonify({
        "item_id": item.id,
        "item_name": item.name,
        "transactions": [tx.to_dict() for tx in transactions]
    }), 200


@inventory_bp.route("/import-csv", methods=["POST"])
@organizer_or_admin_required
def import_inventory_csv():
    """
    Bulk import inventory items from CSV or JSON payload.
    Admin or organizer can import items into the warehouse catalog.
    Handles column normalization, updates existing items if item name exists, or creates new items.
    """
    user = get_current_user()

    raw_rows = []
    # 1. Check if multipart file upload
    if "file" in request.files or "csv_file" in request.files:
        upload_file = request.files.get("file") or request.files.get("csv_file")
        if not upload_file or upload_file.filename == "":
            return jsonify({"error": "No CSV file selected for upload."}), 400
        try:
            content = upload_file.read().decode("utf-8-sig", errors="replace")
            csv_reader = csv.reader(io.StringIO(content))
            raw_rows = list(csv_reader)
        except Exception as e:
            return jsonify({"error": f"Failed to parse CSV file: {str(e)}"}), 400
    # 2. Check if JSON payload with items or raw csv text
    elif request.is_json:
        data = request.get_json() or {}
        if isinstance(data, list):
            items_input = data
        elif "items" in data:
            items_input = data["items"]
        elif "csv_text" in data:
            csv_reader = csv.reader(io.StringIO(data["csv_text"]))
            raw_rows = list(csv_reader)
            items_input = None
        else:
            items_input = None

        if items_input is not None:
            return _process_import_objects(items_input, user)
    else:
        return jsonify({"error": "Please upload a CSV file or submit JSON data."}), 400

    if not raw_rows:
        return jsonify({"error": "The uploaded CSV file is empty."}), 400

    header = raw_rows[0]
    data_rows = raw_rows[1:]

    def normalize_col(name):
        return re.sub(r"[^a-z0-9]", "", str(name).lower())

    col_map = {}
    for idx, col in enumerate(header):
        n = normalize_col(col)
        if n in ("itemname", "name", "item", "title", "product", "equipment"):
            col_map["name"] = idx
        elif n in ("category", "itemcategory", "cat"):
            col_map["category"] = idx
        elif n in ("itemtype", "type", "kind"):
            col_map["item_type"] = idx
        elif n in ("totalstock", "stock", "quantity", "qty", "count", "initialstock"):
            col_map["total_stock"] = idx
        elif n in ("unavailablestock", "unavailable", "damaged", "lost"):
            col_map["unavailable_stock"] = idx
        elif n in ("minimumsafetythreshold", "minimumthreshold", "safetythreshold", "threshold", "minthreshold", "minstock"):
            col_map["minimum_threshold"] = idx
        elif n in ("unit", "unitofmeasure", "uom", "measure"):
            col_map["unit"] = idx
        elif n in ("unitcostinr", "unitcost", "purchasecost", "cost", "price", "rate"):
            col_map["purchase_cost"] = idx
        elif n in ("description", "desc", "notes", "details", "specs"):
            col_map["description"] = idx

    if "name" not in col_map:
        return jsonify({
            "error": "CSV must contain an 'Item Name' or 'Name' column header. Found headers: " + ", ".join(header)
        }), 400

    parsed_items = []
    for row_num, row in enumerate(data_rows, start=2):
        if not row or all(not str(c).strip() for c in row):
            continue

        def get_val(key, default=""):
            if key in col_map and col_map[key] < len(row):
                return str(row[col_map[key]]).strip()
            return default

        item_name = get_val("name")
        if not item_name:
            continue

        category = get_val("category", "Audio")
        if not category:
            category = "Audio"

        raw_type = get_val("item_type", "returnable").lower()
        item_type = "consumable" if "consumable" in raw_type else "returnable"

        try:
            total_stock = int(float(get_val("total_stock", "0") or 0))
        except ValueError:
            total_stock = 0

        try:
            unavailable_stock = int(float(get_val("unavailable_stock", "0") or 0))
        except ValueError:
            unavailable_stock = 0

        try:
            min_thresh = int(float(get_val("minimum_threshold", "5") or 5))
        except ValueError:
            min_thresh = 5

        try:
            cost = float(re.sub(r"[^\d.]", "", get_val("purchase_cost", "0.0") or "0.0") or 0.0)
        except ValueError:
            cost = 0.0

        unit = get_val("unit", "pieces") or "pieces"
        desc = get_val("description", "")

        parsed_items.append({
            "name": item_name,
            "category": category,
            "item_type": item_type,
            "total_stock": max(0, total_stock),
            "unavailable_stock": max(0, unavailable_stock),
            "minimum_threshold": max(0, min_thresh),
            "unit": unit,
            "purchase_cost": max(0.0, cost),
            "description": desc,
            "_row_num": row_num
        })

    return _process_import_objects(parsed_items, user)


def _process_import_objects(items, user):
    if not items:
        return jsonify({"error": "No valid item rows found in CSV."}), 400

    created_count = 0
    updated_count = 0
    skipped_count = 0
    errors = []

    for item_data in items:
        name = (item_data.get("name") or "").strip()
        row_id = item_data.get("_row_num", f"Item '{name}'")
        if not name:
            errors.append(f"Row {row_id}: Missing item name.")
            skipped_count += 1
            continue

        try:
            existing = db_session.query(InventoryItem).filter(InventoryItem.name.ilike(name)).first()
            if existing:
                if not existing.is_active:
                    existing.is_active = True
                
                if item_data.get("category"):
                    existing.category = item_data["category"]
                if item_data.get("unit"):
                    existing.unit = item_data["unit"]
                if item_data.get("description"):
                    existing.description = item_data["description"]
                if "purchase_cost" in item_data:
                    existing.purchase_cost = float(item_data["purchase_cost"])
                if "minimum_threshold" in item_data:
                    existing.minimum_threshold = int(item_data["minimum_threshold"])

                if "total_stock" in item_data:
                    new_total = int(item_data["total_stock"])
                    diff = new_total - existing.total_stock
                    if diff != 0:
                        prev = existing.total_stock
                        existing.total_stock = new_total
                        tx = InventoryTransaction(
                            item_id=existing.id,
                            user_id=user.id,
                            change_amount=diff,
                            previous_total_stock=prev,
                            new_total_stock=new_total,
                            transaction_type=TransactionType.ADJUSTMENT,
                            reason="CSV Bulk Import stock update",
                        )
                        db_session.add(tx)

                db_session.flush()
                check_and_create_stock_alert(db_session, existing.id)
                updated_count += 1
            else:
                item, err = create_item(db_session, item_data, user_id=user.id)
                if err:
                    errors.append(f"Row {row_id} ({name}): {err}")
                    skipped_count += 1
                else:
                    created_count += 1
        except Exception as e:
            errors.append(f"Row {row_id} ({name}): {str(e)}")
            skipped_count += 1

    try:
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        return jsonify({"error": f"Database commit failed: {str(e)}"}), 500

    msg = f"Import completed: {created_count} new item(s) created, {updated_count} existing item(s) updated."
    if errors:
        msg += f" ({len(errors)} skipped due to validation)."

    return jsonify({
        "message": msg,
        "total_rows": len(items),
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "errors": errors[:15],
    }), 200
