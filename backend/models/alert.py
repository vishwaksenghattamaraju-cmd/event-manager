"""Alert model for shortages and low stock warnings."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.models.base import Base


class AlertType:
    SHORTAGE = "shortage"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    HIGH_SHORTAGE_RISK = "high_shortage_risk"
    BOOKING_AT_RISK = "booking_at_risk"
    PREDICTION_DRIFT = "prediction_drift"


class AlertSeverity:
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False, default="WARNING")
    item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True)

    message = Column(Text, nullable=False)
    recommended_action = Column(String(255), nullable=True)

    requested_quantity = Column(Integer, nullable=True)
    available_quantity = Column(Integer, nullable=True)
    shortage_quantity = Column(Integer, nullable=True)

    is_reviewed = Column(Boolean, nullable=False, default=False)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    item = relationship("InventoryItem")
    event = relationship("Event")

    @property
    def is_resolved(self) -> bool:
        return self.is_reviewed

    @is_resolved.setter
    def is_resolved(self, val: bool):
        self.is_reviewed = val
        if val and not self.reviewed_at:
            self.reviewed_at = datetime.now(timezone.utc)

    @property
    def resolved_at(self):
        return self.reviewed_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "item_id": self.item_id,
            "item_name": self.item.name if self.item else None,
            "item_sku": self.item.sku if self.item else None,
            "event_id": self.event_id,
            "event_name": self.event.name if self.event else None,
            "message": self.message,
            "recommended_action": self.recommended_action,
            "requested_quantity": self.requested_quantity,
            "available_quantity": self.available_quantity,
            "shortage_quantity": self.shortage_quantity,
            "is_reviewed": self.is_reviewed,
            "is_resolved": self.is_resolved,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
