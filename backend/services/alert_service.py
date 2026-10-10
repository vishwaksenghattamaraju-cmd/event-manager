"""
Alert Service: Real-time inventory threshold warnings, ML shortage risk monitoring, and alert resolution.
"""

from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.models.alert import Alert, AlertType, AlertSeverity
from backend.models.inventory import InventoryItem


def check_and_create_stock_alert(db: Session, item_id: int) -> Optional[Alert]:
    """
    Checks stock levels for an item and creates or auto-resolves alerts.
    - 0 units available -> CRITICAL Out of Stock alert
    - <= threshold -> WARNING Low Stock alert
    - > threshold -> Auto-resolves previous stock alerts
    """
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item or not item.is_active:
        return None

    net_stock = item.physically_available_base
    threshold = item.minimum_threshold

    if net_stock == 0:
        # Check if already active OUT_OF_STOCK alert exists
        existing = (
            db.query(Alert)
            .filter(
                Alert.item_id == item.id,
                Alert.alert_type == AlertType.OUT_OF_STOCK,
                Alert.is_reviewed.is_(False),
            )
            .first()
        )
        if existing:
            return existing

        alert = Alert(
            alert_type=AlertType.OUT_OF_STOCK,
            severity=AlertSeverity.CRITICAL,
            item_id=item.id,
            message=f"Out of Stock: '{item.name}' has 0 available units remaining in warehouse.",
            recommended_action=f"Order emergency restock for '{item.name}' immediately.",
            requested_quantity=None,
            available_quantity=0,
            shortage_quantity=threshold,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    elif net_stock <= threshold:
        # Check if already active LOW_STOCK alert exists
        existing = (
            db.query(Alert)
            .filter(
                Alert.item_id == item.id,
                Alert.alert_type == AlertType.LOW_STOCK,
                Alert.is_reviewed.is_(False),
            )
            .first()
        )
        if existing:
            return existing

        alert = Alert(
            alert_type=AlertType.LOW_STOCK,
            severity=AlertSeverity.WARNING,
            item_id=item.id,
            message=(
                f"Low Stock Warning: '{item.name}' has only {net_stock} units available "
                f"(safety threshold is {threshold})."
            ),
            recommended_action=f"Procure additional stock for '{item.name}' before upcoming bookings.",
            requested_quantity=None,
            available_quantity=net_stock,
            shortage_quantity=threshold - net_stock,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    else:
        # Stock replenished above threshold: auto-resolve active stock alerts for this item
        active_stock_alerts = (
            db.query(Alert)
            .filter(
                Alert.item_id == item.id,
                Alert.alert_type.in_([AlertType.LOW_STOCK, AlertType.OUT_OF_STOCK]),
                Alert.is_reviewed.is_(False),
            )
            .all()
        )
        for a in active_stock_alerts:
            a.is_resolved = True
        if active_stock_alerts:
            db.commit()
        return None


def create_ml_shortage_risk_alert(
    db: Session,
    item_id: int,
    risk_score: float,
    risk_level: str,
    reason: str,
) -> Optional[Alert]:
    """
    Creates an alert when ML Model 2 flags an item with High or Medium shortage risk.
    """
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item or not item.is_active:
        return None

    clean_level = risk_level.capitalize()
    if clean_level not in ("High", "Medium"):
        return None

    severity = AlertSeverity.CRITICAL if clean_level == "High" else AlertSeverity.WARNING

    # Check for active existing risk alert for this item
    existing = (
        db.query(Alert)
        .filter(
            Alert.item_id == item.id,
            Alert.alert_type == AlertType.HIGH_SHORTAGE_RISK,
            Alert.is_reviewed.is_(False),
        )
        .first()
    )
    if existing:
        existing.message = f"{clean_level} Shortage Risk ({int(risk_score * 100)}%): {reason}"
        existing.severity = severity
        db.commit()
        return existing

    alert = Alert(
        alert_type=AlertType.HIGH_SHORTAGE_RISK,
        severity=severity,
        item_id=item.id,
        message=f"{clean_level} Shortage Risk ({int(risk_score * 100)}%): {reason}",
        recommended_action="Review upcoming schedule and consider procurement or booking rescheduling.",
        requested_quantity=None,
        available_quantity=item.physically_available_base,
        shortage_quantity=None,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def get_active_alerts(db: Session, severity: Optional[str] = None) -> List[Alert]:
    """Retrieves all unresolved alerts ordered by severity and recency."""
    query = db.query(Alert).filter(Alert.is_reviewed.is_(False))
    if severity:
        query = query.filter(Alert.severity == severity.upper())

    alerts = query.order_by(Alert.created_at.desc()).all()

    # Sort so CRITICAL appears before WARNING and INFO
    severity_order = {AlertSeverity.CRITICAL: 0, AlertSeverity.WARNING: 1, AlertSeverity.INFO: 2}
    alerts.sort(key=lambda a: severity_order.get(a.severity, 99))
    return alerts


def resolve_alert(db: Session, alert_id: int, user_id: Optional[int] = None) -> Tuple[Optional[Alert], Optional[str]]:
    """Resolves an alert (marks is_resolved = True)."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None, "Alert not found."

    alert.is_resolved = True
    alert.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert, None


def scan_all_inventory_and_generate_alerts(db: Session) -> List[Alert]:
    """Scans all active catalog items and generates stock and ML alerts."""
    from backend.services.ml_service import get_ml_service
    ml_service = get_ml_service()

    items = db.query(InventoryItem).filter(InventoryItem.is_active.is_(True)).all()
    generated = []

    for item in items:
        # 1. Stock threshold alert
        stk_alert = check_and_create_stock_alert(db, item.id)
        if stk_alert and not stk_alert.is_resolved:
            generated.append(stk_alert)

        # 2. ML Shortage Risk alert
        risk = ml_service.assess_shortage_risk(item.id, db, days_ahead=14)
        if risk.get("risk_level") in ("High", "Medium"):
            ml_alert = create_ml_shortage_risk_alert(
                db=db,
                item_id=item.id,
                risk_score=risk.get("risk_score", 0.8),
                risk_level=risk.get("risk_level", "High"),
                reason=risk.get("reason", "Upcoming reservation commitments exceed buffer."),
            )
            if ml_alert and not ml_alert.is_resolved:
                generated.append(ml_alert)

    return generated
