"""Inventory service: encapsulates stock management, audit trails, and soft-delete business rules."""

from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_
from backend.models.inventory import (
    InventoryItem,
    InventoryTransaction,
    ItemType,
    TransactionType,
)
from backend.services.alert_service import check_and_create_stock_alert


def get_all_items(
    db: Session,
    include_inactive: bool = False,
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> List[InventoryItem]:
    """Retrieves inventory items with optional search and category filters."""
    query = db.query(InventoryItem)

    if not include_inactive:
        query = query.filter(InventoryItem.is_active.is_(True))

    if category:
        query = query.filter(InventoryItem.category == category.strip())

    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                InventoryItem.name.ilike(search_pattern),
                InventoryItem.description.ilike(search_pattern),
            )
        )

    return query.order_by(InventoryItem.category.asc(), InventoryItem.name.asc()).all()


def get_item_by_id(db: Session, item_id: int) -> Optional[InventoryItem]:
    """Fetches a single inventory item by ID."""
    return db.query(InventoryItem).filter(InventoryItem.id == item_id).first()


def create_item(
    db: Session, data: Dict[str, Any], user_id: Optional[int] = None
) -> Tuple[Optional[InventoryItem], Optional[str]]:
    """
    Creates a new inventory item and logs the initial stock in inventory_transactions.
    """
    name = (data.get("name") or "").strip()
    category = (data.get("category") or "").strip()
    item_type = data.get("item_type")
    if not item_type:
        item_type = ItemType.CONSUMABLE if data.get("is_consumable") else ItemType.RETURNABLE
    item_type = item_type.strip().lower()

    if not name:
        return None, "Item name is required."
    if not category:
        return None, "Item category is required."
    if item_type not in ItemType.ALL_TYPES:
        return None, f"Invalid item type '{item_type}'. Must be 'returnable' or 'consumable'."

    # Check for unique name
    existing = db.query(InventoryItem).filter(InventoryItem.name.ilike(name)).first()
    if existing:
        return None, f"An item with the name '{name}' already exists."

    try:
        total_stock = int(data.get("total_stock", 0))
        if total_stock < 0:
            return None, "Initial total stock cannot be negative."

        unavailable_stock = int(data.get("unavailable_stock", 0))
        if unavailable_stock < 0:
            return None, "Unavailable stock cannot be negative."
        if unavailable_stock > total_stock:
            return None, "Unavailable stock cannot exceed total stock."

        minimum_threshold = int(data.get("minimum_threshold", 5))
        if minimum_threshold < 0:
            return None, "Minimum threshold cannot be negative."

        purchase_cost = float(data.get("purchase_cost", 0.0))
        if purchase_cost < 0:
            return None, "Purchase cost cannot be negative."

        item = InventoryItem(
            name=name,
            category=category,
            description=(data.get("description") or "").strip(),
            item_type=item_type,
            total_stock=total_stock,
            unavailable_stock=unavailable_stock,
            minimum_threshold=minimum_threshold,
            unit=(data.get("unit") or "pieces").strip(),
            purchase_cost=purchase_cost,
            is_active=True,
        )
        db.add(item)
        db.flush()  # Generate item.id

        # Write initial transaction record
        tx = InventoryTransaction(
            item_id=item.id,
            user_id=user_id,
            change_amount=total_stock,
            previous_total_stock=0,
            new_total_stock=total_stock,
            transaction_type=TransactionType.INITIAL,
            reason="Initial item inventory registration",
        )
        db.add(tx)
        db.commit()
        db.refresh(item)
        check_and_create_stock_alert(db, item.id)
        return item, None
    except ValueError as e:
        db.rollback()
        return None, f"Validation error: {str(e)}"
    except Exception as e:
        db.rollback()
        return None, f"Failed to create inventory item: {str(e)}"


def update_item(
    db: Session, item_id: int, data: Dict[str, Any], user_id: Optional[int] = None
) -> Tuple[Optional[InventoryItem], Optional[str]]:
    """
    Updates item metadata and adjusts stock if total_stock is changed.
    Ensures an immutable transaction is written if stock changes.
    """
    item = get_item_by_id(db, item_id)
    if not item:
        return None, "Inventory item not found."

    # Validate name uniqueness if changed
    new_name = (data.get("name") or "").strip()
    if new_name and new_name.lower() != item.name.lower():
        existing = db.query(InventoryItem).filter(InventoryItem.name.ilike(new_name)).first()
        if existing and existing.id != item.id:
            return None, f"Another item named '{new_name}' already exists."
        item.name = new_name

    if "category" in data and data["category"]:
        item.category = data["category"].strip()

    if "description" in data:
        item.description = (data["description"] or "").strip()

    if "unit" in data and data["unit"]:
        item.unit = data["unit"].strip()

    if "minimum_threshold" in data:
        try:
            val = int(data["minimum_threshold"])
            if val < 0:
                return None, "Minimum threshold cannot be negative."
            item.minimum_threshold = val
        except ValueError:
            return None, "Invalid minimum threshold number."

    if "purchase_cost" in data:
        try:
            val = float(data["purchase_cost"])
            if val < 0:
                return None, "Purchase cost cannot be negative."
            item.purchase_cost = val
        except ValueError:
            return None, "Invalid purchase cost number."

    # Handle total_stock change if requested
    if "total_stock" in data:
        try:
            new_total = int(data["total_stock"])
            if new_total < 0:
                return None, "Total stock cannot be negative."

            if new_total < item.unavailable_stock:
                return None, (
                    f"New total stock ({new_total}) cannot be less than "
                    f"currently unavailable stock ({item.unavailable_stock})."
                )

            diff = new_total - item.total_stock
            if diff != 0:
                old_total = item.total_stock
                item.total_stock = new_total
                tx_type = TransactionType.STOCK_IN if diff > 0 else TransactionType.STOCK_OUT
                reason = data.get("reason") or "Manual total stock update"

                tx = InventoryTransaction(
                    item_id=item.id,
                    user_id=user_id,
                    change_amount=diff,
                    previous_total_stock=old_total,
                    new_total_stock=new_total,
                    transaction_type=tx_type,
                    reason=reason,
                )
                db.add(tx)
        except ValueError:
            return None, "Total stock must be a valid integer."

    try:
        item.validate_quantities()
        db.commit()
        db.refresh(item)
        check_and_create_stock_alert(db, item.id)
        return item, None
    except ValueError as e:
        db.rollback()
        return None, str(e)
    except Exception as e:
        db.rollback()
        return None, f"Failed to update item: {str(e)}"


def adjust_stock(
    db: Session,
    item_id: int,
    change_amount: int,
    reason: str,
    user_id: Optional[int] = None,
    transaction_type: str = TransactionType.ADJUSTMENT,
) -> Tuple[Optional[InventoryItem], Optional[str]]:
    """
    Adjusts item physical stock by a positive or negative quantity.
    Prevents negative stock, writes an immutable transaction log.
    """
    item = get_item_by_id(db, item_id)
    if not item:
        return None, "Inventory item not found."

    if change_amount == 0:
        return item, None

    old_total = item.total_stock
    new_total = old_total + change_amount

    if new_total < 0:
        return None, f"Stock adjustment would result in negative stock ({new_total}). Operation rejected."

    if new_total < item.unavailable_stock:
        return None, (
            f"Resulting total stock ({new_total}) cannot be less than "
            f"unavailable stock ({item.unavailable_stock})."
        )

    try:
        item.total_stock = new_total
        tx = InventoryTransaction(
            item_id=item.id,
            user_id=user_id,
            change_amount=change_amount,
            previous_total_stock=old_total,
            new_total_stock=new_total,
            transaction_type=transaction_type,
            reason=reason.strip() if reason else "Manual stock adjustment",
        )
        db.add(tx)
        db.commit()
        db.refresh(item)
        check_and_create_stock_alert(db, item.id)
        return item, None
    except Exception as e:
        db.rollback()
        return None, f"Adjustment failed: {str(e)}"


def mark_stock_unavailable(
    db: Session,
    item_id: int,
    amount: int,
    reason: str,
    user_id: Optional[int] = None,
    status_kind: str = "damaged",
) -> Tuple[Optional[InventoryItem], Optional[str]]:
    """
    Marks an amount of stock as damaged or in maintenance (temporarily unavailable).
    """
    item = get_item_by_id(db, item_id)
    if not item:
        return None, "Inventory item not found."

    if amount < 0:
        return None, "Quantity must be non-negative."

    new_unavailable = item.unavailable_stock + amount
    if new_unavailable > item.total_stock:
        return None, (
            f"Cannot mark {amount} as unavailable; total unavailable would be "
            f"{new_unavailable}, which exceeds total stock ({item.total_stock})."
        )

    try:
        item.unavailable_stock = new_unavailable
        tx_type = TransactionType.DAMAGED if status_kind == "damaged" else TransactionType.MAINTENANCE
        tx = InventoryTransaction(
            item_id=item.id,
            user_id=user_id,
            change_amount=0,  # Total stock physically still exists, but is unusable
            previous_total_stock=item.total_stock,
            new_total_stock=item.total_stock,
            transaction_type=tx_type,
            reason=reason.strip() or f"Marked {amount} items as {status_kind}",
        )
        db.add(tx)
        db.commit()
        db.refresh(item)
        check_and_create_stock_alert(db, item.id)
        return item, None
    except Exception as e:
        db.rollback()
        return None, f"Failed to update unavailable stock: {str(e)}"


def deactivate_item(
    db: Session, item_id: int, user_id: Optional[int] = None
) -> Tuple[Optional[InventoryItem], Optional[str]]:
    """
    Soft-deletes an item (is_active = False).
    IMPORTANT: Never hard-deletes an item with transaction history.
    """
    item = get_item_by_id(db, item_id)
    if not item:
        return None, "Inventory item not found."

    try:
        item.is_active = False
        tx = InventoryTransaction(
            item_id=item.id,
            user_id=user_id,
            change_amount=0,
            previous_total_stock=item.total_stock,
            new_total_stock=item.total_stock,
            transaction_type=TransactionType.ADJUSTMENT,
            reason="Item deactivated (soft delete)",
        )
        db.add(tx)
        db.commit()
        db.refresh(item)
        return item, None
    except Exception as e:
        db.rollback()
        return None, f"Failed to deactivate item: {str(e)}"


def get_item_transactions(db: Session, item_id: int) -> List[InventoryTransaction]:
    """Returns the complete, immutable transaction history for an item."""
    return (
        db.query(InventoryTransaction)
        .filter(InventoryTransaction.item_id == item_id)
        .order_by(InventoryTransaction.created_at.desc())
        .all()
    )
