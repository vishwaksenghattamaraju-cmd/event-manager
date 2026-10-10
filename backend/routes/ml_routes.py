"""
Machine Learning API routes: item quantity prediction, shortage risk radar, and model retraining.
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from backend.models.base import db_session
from backend.routes.auth_routes import organizer_or_admin_required, admin_required, get_current_user
from backend.services.ml_service import get_ml_service
from backend.services.event_service import parse_datetime_utc

ml_bp = Blueprint("ml", __name__, url_prefix="/api/ml")


@ml_bp.route("/predict-items", methods=["POST"])
@organizer_or_admin_required
def predict_recommended_items():
    """
    Recommends inventory item types and quantities for an event.
    ML provides intelligent recommendations; backend enforces warehouse availability.
    """
    data = request.get_json(silent=True) or {}

    event_type = data.get("event_type", "conference")
    expected_guests = data.get("expected_guests")
    if expected_guests is None:
        expected_guests = data.get("expected_attendees", 50)

    try:
        expected_guests = int(expected_guests)
    except (ValueError, TypeError):
        expected_guests = 50

    duration_hours = float(data.get("duration_hours", 4.0))
    respect_stock = bool(data.get("respect_stock", False))

    event_date = None
    start_time_raw = data.get("start_time") or data.get("event_date")
    if start_time_raw:
        try:
            event_date = parse_datetime_utc(start_time_raw)
        except Exception:
            event_date = None

    ml_service = get_ml_service()
    prediction_result = ml_service.predict_quantities(
        event_type=event_type,
        expected_guests=expected_guests,
        duration_hours=duration_hours,
        event_date=event_date,
        respect_stock=respect_stock,
        db=db_session,
    )

    return jsonify(prediction_result), 200


@ml_bp.route("/shortage-risks", methods=["GET"])
@organizer_or_admin_required
def get_shortage_risks():
    """
    Returns items flagged with Medium or High shortage risk over the upcoming reservation horizon.
    """
    days_ahead = int(request.args.get("days_ahead", 14))
    min_level = request.args.get("min_level", "medium")

    ml_service = get_ml_service()
    risks = ml_service.get_all_shortage_risks(
        db=db_session,
        days_ahead=days_ahead,
        min_level=min_level,
    )

    return jsonify({
        "timestamp": datetime.now().isoformat(),
        "horizon_days": days_ahead,
        "risks_count": len(risks),
        "items_at_risk": risks,
    }), 200


@ml_bp.route("/retrain", methods=["POST"])
@admin_required
def retrain_models_endpoint():
    """
    Triggers model retraining, writes new weights to disk, and logs run into model_runs table.
    Admin only.
    """
    user = get_current_user()
    ml_service = get_ml_service()

    result = ml_service.retrain_models(db=db_session, user_id=user.id)
    return jsonify(result), 200
