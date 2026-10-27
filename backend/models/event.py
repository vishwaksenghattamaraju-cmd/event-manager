"""Event and EventItem models for event bookings and stock allocations."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import relationship
from backend.models.base import Base


class EventStatus:
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ALL_STATUSES = (DRAFT, CONFIRMED, CANCELLED, COMPLETED)


class EventType:
    BIRTHDAY = "birthday"
    WEDDING = "wedding"
    CORPORATE = "corporate"
    CONFERENCE = "conference"
    OTHER = "other"
    ALL_TYPES = (BIRTHDAY, WEDDING, CORPORATE, CONFERENCE, OTHER)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organizer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    event_type = Column(String(50), nullable=False, default=EventType.OTHER)
    location = Column(String(200), nullable=True)
    image_url = Column(Text, nullable=True)

    # All datetimes stored in UTC
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False, index=True)

    # Optional buffer in minutes for setup and teardown
    setup_buffer_minutes = Column(Integer, nullable=False, default=0)
    teardown_buffer_minutes = Column(Integer, nullable=False, default=0)

    expected_guest_count = Column(Integer, nullable=False, default=50)
    status = Column(String(20), nullable=False, default=EventStatus.DRAFT, index=True)

    # Idempotency token to prevent duplicate confirmations
    idempotency_key = Column(String(100), nullable=True, unique=True, index=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    organizer = relationship("User", backref="events")
    items = relationship("EventItem", back_populates="event", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_events_window", "status", "start_time", "end_time"),
    )

    def to_dict(self, include_items: bool = True) -> dict:
        data = {
            "id": self.id,
            "organizer_id": self.organizer_id,
            "organizer_name": self.organizer.username if self.organizer else None,
            "name": self.name,
            "event_type": self.event_type,
            "location": self.location,
            "image_url": self.image_url,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "setup_buffer_minutes": self.setup_buffer_minutes,
            "teardown_buffer_minutes": self.teardown_buffer_minutes,
            "expected_guest_count": self.expected_guest_count,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_items:
            data["items"] = [item.to_dict() for item in self.items]
        return data


class EventItem(Base):
    """Associates required inventory items and allocated quantities to an event."""
    __tablename__ = "event_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Requested quantity vs allocated quantity
    # Only confirmed events have allocated_quantity > 0
    quantity = Column(Integer, nullable=False)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    event = relationship("Event", back_populates="items")
    item = relationship("InventoryItem")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "item_id": self.item_id,
            "item_name": self.item.name if self.item else None,
            "item_type": self.item.item_type if self.item else None,
            "quantity": self.quantity,
            "unit": self.item.unit if self.item else "pieces",
        }
