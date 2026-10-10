"""
Automated tests for Phase 5: Machine Learning Models & Intelligence Layer.

Covers:
- Test #17: ML prediction returns sensible numbers (non-negative, scales with guest count)
- Test #18: ML model fallback works when inputs are extreme or model is missing
- Test #19: Shortage risk scoring classifies properly (high risk when demand > stock)
- Test #20: Retrain endpoint trains model and logs to ml_runs table
- Test #21: Recommendations respect backend stock reality (suggested <= available when flag set)
"""

from datetime import datetime, timezone, timedelta
import pytest
from backend.models.base import db_session
from backend.models.inventory import InventoryItem, ItemType
from backend.models.event import Event, EventItem, EventStatus, EventType
from backend.models.ml_run import ModelRun
from backend.services.ml_service import get_ml_service, MLService


def test_test17_ml_prediction_returns_sensible_numbers(organizer_client):
    """
    Test #17: ML prediction returns non-negative numbers and scales proportionally with guest count.
    Confidence intervals are valid (confidence_lower <= suggested <= confidence_upper).
    """
    # 1. Prediction for small event (30 guests)
    resp_small = organizer_client.post("/api/ml/predict-items", json={
        "event_type": "conference",
        "expected_guests": 30,
        "duration_hours": 4.0,
    })
    assert resp_small.status_code == 200, f"Small event prediction failed: {resp_small.get_json()}"
    data_small = resp_small.get_json()
    items_small = {item["item_key"]: item for item in data_small["items"]}

    assert items_small["chairs"]["suggested_quantity"] >= 30
    assert items_small["chairs"]["suggested_quantity"] <= 45
    assert items_small["chairs"]["confidence_lower"] <= items_small["chairs"]["suggested_quantity"]
    assert items_small["chairs"]["suggested_quantity"] <= items_small["chairs"]["confidence_upper"]

    # 2. Prediction for large event (200 guests)
    resp_large = organizer_client.post("/api/ml/predict-items", json={
        "event_type": "conference",
        "expected_guests": 200,
        "duration_hours": 8.0,
    })
    assert resp_large.status_code == 200
    data_large = resp_large.get_json()
    items_large = {item["item_key"]: item for item in data_large["items"]}

    # Non-negative checks across all items
    for item in data_large["items"]:
        assert item["suggested_quantity"] >= 0
        assert item["confidence_lower"] >= 0
        assert item["confidence_upper"] >= item["suggested_quantity"]

    # Scaling check: 200 guests requires significantly more chairs and tables than 30 guests
    assert items_large["chairs"]["suggested_quantity"] > items_small["chairs"]["suggested_quantity"] * 4
    assert items_large["tables"]["suggested_quantity"] > items_small["tables"]["suggested_quantity"] * 4
    assert items_large["microphones"]["suggested_quantity"] >= items_small["microphones"]["suggested_quantity"]


def test_test18_ml_fallback_on_extreme_inputs_or_missing_model(organizer_client, monkeypatch):
    """
    Test #18: Fallback mechanism activates safely on extreme/invalid inputs or missing model files.
    Never crashes with 500 and never returns negative values.
    """
    # 1. Negative guest count
    resp_neg = organizer_client.post("/api/ml/predict-items", json={
        "event_type": "wedding",
        "expected_guests": -50,
    })
    assert resp_neg.status_code == 200
    data_neg = resp_neg.get_json()
    assert data_neg["is_fallback"] is True
    for item in data_neg["items"]:
        assert item["suggested_quantity"] >= 0

    # 2. Outrageously extreme guest count (e.g. 500,000 guests)
    resp_extreme = organizer_client.post("/api/ml/predict-items", json={
        "event_type": "conference",
        "expected_guests": 500000,
    })
    assert resp_extreme.status_code == 200
    data_extreme = resp_extreme.get_json()
    assert data_extreme["is_fallback"] is True

    # 3. Simulated missing model pipeline
    ml_service = get_ml_service()
    original_predictor = ml_service._predictor
    try:
        ml_service._predictor = None
        resp_missing = organizer_client.post("/api/ml/predict-items", json={
            "event_type": "birthday",
            "expected_guests": 40,
        })
        assert resp_missing.status_code == 200
        data_missing = resp_missing.get_json()
        assert data_missing["is_fallback"] is True
        assert len(data_missing["items"]) > 0
        chairs_pred = next(i for i in data_missing["items"] if i["item_key"] == "chairs")
        assert chairs_pred["suggested_quantity"] >= 40
    finally:
        ml_service._predictor = original_predictor


def test_test19_shortage_risk_classification(organizer_client, organizer_user, sample_chair):
    """
    Test #19: Shortage risk classifier accurately identifies high vs low risk items
    based on confirmed bookings in the upcoming horizon.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ml_service = get_ml_service()

    # 1. Initial state: sample_chair has 100 available, 0 reserved -> LOW RISK
    risk_initial = ml_service.assess_shortage_risk(sample_chair.id, db_session, days_ahead=14)
    assert risk_initial["risk_level"] == "Low"
    assert risk_initial["risk_score"] < 0.35

    # 2. Add an event reserving 95 chairs in the upcoming week (leaves only 5 chairs vs threshold of 10)
    conflict_event = Event(
        organizer_id=organizer_user.id,
        name="Upcoming Megaconference",
        event_type=EventType.CONFERENCE,
        start_time=now + timedelta(days=3),
        end_time=now + timedelta(days=3, hours=8),
        status=EventStatus.CONFIRMED,
        expected_guest_count=100,
    )
    db_session.add(conflict_event)
    db_session.flush()

    evt_item = EventItem(
        event_id=conflict_event.id,
        item_id=sample_chair.id,
        quantity=95,
    )
    db_session.add(evt_item)
    db_session.commit()

    # 3. High risk evaluation
    risk_high = ml_service.assess_shortage_risk(sample_chair.id, db_session, days_ahead=14)
    assert risk_high["risk_level"] == "High"
    assert risk_high["risk_score"] >= 0.70
    assert "High risk" in risk_high["reason"]

    # 4. API endpoint /api/ml/shortage-risks returns the high risk item
    resp = organizer_client.get("/api/ml/shortage-risks?days_ahead=14&min_level=medium")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["risks_count"] >= 1
    flagged_ids = [r["item_id"] for r in data["items_at_risk"]]
    assert sample_chair.id in flagged_ids


def test_test20_retrain_endpoint_governance_and_rbac(admin_client, organizer_client):
    """
    Test #20: Retrain endpoint trains models, records metrics, and audits the run in model_runs.
    Enforces that non-admin accounts are rejected with 403 Forbidden.
    """
    # 1. Organizer attempts retrain -> 403 Forbidden
    resp_org = organizer_client.post("/api/ml/retrain")
    assert resp_org.status_code == 403

    # 2. Admin calls retrain -> 200 OK
    initial_runs_count = db_session.query(ModelRun).count()

    resp_admin = admin_client.post("/api/ml/retrain")
    assert resp_admin.status_code == 200
    result = resp_admin.get_json()
    assert result["success"] is True
    assert "model_run" in result
    assert result["model_run"]["mae"] is not None
    assert result["model_run"]["r2_score"] is not None

    # 3. Verify new record in database model_runs table
    new_runs_count = db_session.query(ModelRun).count()
    assert new_runs_count == initial_runs_count + 1

    latest_run = db_session.query(ModelRun).order_by(ModelRun.id.desc()).first()
    assert latest_run.model_name == "RandomForestRegressor + Classifier"
    assert latest_run.training_samples_count >= 1000
    assert latest_run.mae <= 2.0  # MAE should be low and accurate


def test_test21_recommendations_respect_backend_stock_reality(organizer_client, admin_user):
    """
    Test #21: Golden Rule verification:
    If warehouse has limited stock, respect_stock=True caps the recommendation to warehouse reality.
    """
    # 1. Create a scarce item: Only 8 Luxury Sofas exist in warehouse
    scarce_item = InventoryItem(
        name="Luxury Velvet Sofa",
        category="Furniture",
        item_type=ItemType.RETURNABLE,
        total_stock=8,
        unavailable_stock=0,
        minimum_threshold=2,
        is_active=True,
    )
    db_session.add(scarce_item)
    db_session.commit()

    # 2. Predict for large wedding (200 guests) with respect_stock=False
    resp_unconstrained = organizer_client.post("/api/ml/predict-items", json={
        "event_type": "wedding",
        "expected_guests": 200,
        "respect_stock": False,
    })
    assert resp_unconstrained.status_code == 200
    data_uncon = resp_unconstrained.get_json()
    chair_rec_uncon = next(i for i in data_uncon["items"] if i["item_key"] == "chairs")
    assert chair_rec_uncon["suggested_quantity"] >= 200  # Raw model wants ~220 chairs

    # 3. Predict for 200 guests with respect_stock=True
    resp_constrained = organizer_client.post("/api/ml/predict-items", json={
        "event_type": "wedding",
        "expected_guests": 200,
        "respect_stock": True,
    })
    assert resp_constrained.status_code == 200
    data_con = resp_constrained.get_json()

    # If any matching warehouse item exists with limited quantity, suggested <= available
    for item in data_con["items"]:
        if item["available_in_warehouse"] is not None:
            assert item["suggested_quantity"] <= item["available_in_warehouse"]
            if item["model_raw_quantity"] > item["available_in_warehouse"]:
                assert item["is_stock_constrained"] is True
