"""Inventory models: InventoryItem and immutable InventoryTransaction audit log."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.models.base import Base


class ItemType:
    RETURNABLE = "returnable"  # Chairs, tables, speakers (returned after event)
    CONSUMABLE = "consumable"  # Food, flowers, napkins, confetti (consumed/subtracted)
    ALL_TYPES = (RETURNABLE, CONSUMABLE)


class TransactionType:
    INITIAL = "initial"
    STOCK_IN = "stock_in"
    STOCK_OUT = "stock_out"
    ADJUSTMENT = "adjustment"
    DAMAGED = "damaged"
    MAINTENANCE = "maintenance"
    CONSUMED = "consumed"
    ALL_TYPES = (INITIAL, STOCK_IN, STOCK_OUT, ADJUSTMENT, DAMAGED, MAINTENANCE, CONSUMED)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    category = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)
    item_type = Column(String(20), nullable=False, default=ItemType.RETURNABLE)

    # Physical quantities
    total_stock = Column(Integer, nullable=False, default=0)
    unavailable_stock = Column(Integer, nullable=False, default=0)
    minimum_threshold = Column(Integer, nullable=False, default=5)
    unit = Column(String(20), nullable=False, default="pieces")
    purchase_cost = Column(Float, nullable=True, default=0.0)

    # Status & Timestamps
    is_active = Column(Boolean, nullable=False, default=True)  # Soft delete
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    transactions = relationship(
        "InventoryTransaction",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="desc(InventoryTransaction.created_at)"
    )

    def validate_quantities(self):
        """Ensures that physical stock counts remain valid and non-negative."""
        if self.total_stock < 0:
            raise ValueError(f"Total stock cannot be negative: {self.total_stock}")
        if self.unavailable_stock < 0:
            raise ValueError(f"Unavailable stock cannot be negative: {self.unavailable_stock}")
        if self.unavailable_stock > self.total_stock:
            raise ValueError(
                f"Unavailable stock ({self.unavailable_stock}) cannot exceed total stock ({self.total_stock})"
            )

    @property
    def physically_available_base(self) -> int:
        """
        Stock that is physically sound (not damaged or in maintenance),
        before considering any event-specific time window reservations.
        """
        return max(0, self.total_stock - self.unavailable_stock)

    @property
    def sku(self) -> str:
        """Dynamic SKU code: INV-<CAT>-<ID:04d>"""
        cat_prefix = (self.category or "GEN")[:3].upper()
        item_id = self.id or 0
        return f"INV-{cat_prefix}-{item_id:04d}"

    @property
    def status(self) -> str:
        """Calculates dynamic inventory stock status."""
        avail = self.physically_available_base
        if avail == 0:
            return "out_of_stock"
        if avail <= self.minimum_threshold:
            return "low_stock"
        return "in_stock"

    def to_dict(self) -> dict:
        """Serializes inventory item details."""
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "item_type": self.item_type,
            "total_stock": self.total_stock,
            "unavailable_stock": self.unavailable_stock,
            "physically_available_base": self.physically_available_base,
            "minimum_threshold": self.minimum_threshold,
            "unit": self.unit,
            "purchase_cost": self.purchase_cost,
            "status": self.status,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class InventoryTransaction(Base):
    """
    Append-only audit trail of every stock modification.
    Never modified or deleted.
    """
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    change_amount = Column(Integer, nullable=False)
    previous_total_stock = Column(Integer, nullable=False)
    new_total_stock = Column(Integer, nullable=False)
    transaction_type = Column(String(30), nullable=False)
    reason = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    item = relationship("InventoryItem", back_populates="transactions")
    user = relationship("User")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item_name": self.item.name if self.item else None,
            "user_id": self.user_id,
            "username": self.user.username if self.user else "System",
            "change_amount": self.change_amount,
            "previous_total_stock": self.previous_total_stock,
            "new_total_stock": self.new_total_stock,
            "transaction_type": self.transaction_type,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
