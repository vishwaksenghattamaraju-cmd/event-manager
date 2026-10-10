"""Alert API routes: real-time shortage and low-stock alerts and resolution."""

from flask import Blueprint, jsonify, request
from backend.models.base import db_session
from backend.routes.auth_routes import organizer_or_admin_required, admin_required, get_current_user
from backend.services.alert_service import (
    get_active_alerts,
    resolve_alert,
    scan_all_inventory_and_generate_alerts,
)

alert_bp = Blueprint("alerts", __name__, url_prefix="/api/alerts")


@alert_bp.route("", methods=["GET"])
@organizer_or_admin_required
def list_active_alerts():
    """
    Returns all unresolved active alerts, ordered by severity and recency.
    Optional query param: ?severity=CRITICAL|WARNING|INFO
    """
    severity = request.args.get("severity")
    alerts = get_active_alerts(db_session, severity=severity)

    critical_count = sum(1 for a in alerts if a.severity == "CRITICAL")
    warning_count = sum(1 for a in alerts if a.severity == "WARNING")

    return jsonify({
        "total_active": len(alerts),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "alerts": [a.to_dict() for a in alerts],
    }), 200


@alert_bp.route("/<int:alert_id>/resolve", methods=["POST"])
@organizer_or_admin_required
def resolve_alert_endpoint(alert_id: int):
    """
    Marks an alert as resolved/reviewed.
    """
    user = get_current_user()
    resolved_alert, err = resolve_alert(db_session, alert_id, user_id=user.id if user else None)
    if err:
        return jsonify({"error": err}), 404

    return jsonify({
        "message": f"Alert #{alert_id} resolved successfully.",
        "alert": resolved_alert.to_dict(),
    }), 200


@alert_bp.route("/scan", methods=["POST"])
@admin_required
def trigger_alert_scan():
    """
    Scans all catalog items for threshold breaches and ML shortage risks.
    """
    generated = scan_all_inventory_and_generate_alerts(db_session)
    return jsonify({
        "message": f"Scan completed. Generated {len(generated)} active alerts.",
        "generated_count": len(generated),
        "alerts": [a.to_dict() for a in generated],
    }), 200
