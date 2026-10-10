"""Inventory routes: CRUD, stock adjustment, and transaction history endpoints."""

from flask import Blueprint, request, jsonify
from backend.models.base import db_session
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
