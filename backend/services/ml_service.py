"""
Machine Learning Service: Prediction, Shortage Risk Classification, and Model Governance.

GOLDEN RULE:
ML only RECOMMENDS; backend and database ENFORCE.
The ML model has zero authority to allocate or reserve stock.
"""

import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
import joblib
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.inventory import InventoryItem
from backend.models.event import Event, EventItem, EventStatus
from backend.models.ml_run import ModelRun

ML_DIR = Path(__file__).resolve().parent.parent.parent / "ml"
MODELS_DIR = ML_DIR / "models"


class MLService:
    def __init__(self):
        self.predictor_path = MODELS_DIR / "quantity_predictor.joblib"
        self.classifier_path = MODELS_DIR / "shortage_classifier.joblib"
        self.metadata_path = MODELS_DIR / "metadata.json"
        self._predictor = None
        self._classifier = None
        self._load_models()

    def _load_models(self):
        """Loads trained pipelines from disk if present."""
        if self.predictor_path.exists():
            try:
                self._predictor = joblib.load(self.predictor_path)
            except Exception as e:
                print(f"Warning: Failed to load quantity predictor: {e}")
                self._predictor = None

        if self.classifier_path.exists():
            try:
                self._classifier = joblib.load(self.classifier_path)
            except Exception as e:
                print(f"Warning: Failed to load shortage classifier: {e}")
                self._classifier = None

    def reload(self):
        """Reloads model artifacts from disk."""
        self._load_models()

    @staticmethod
    def get_season(dt: datetime) -> str:
        """Determines season from datetime."""
        month = dt.month
        if month in (3, 4, 5):
            return "spring"
        elif month in (6, 7, 8):
            return "summer"
        elif month in (9, 10, 11):
            return "fall"
        return "winter"

    def predict_quantities(
        self,
        event_type: str,
        expected_guests: int,
        duration_hours: float = 4.0,
        event_date: Optional[datetime] = None,
        respect_stock: bool = False,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Recommends inventory quantities for core item categories based on event profile.
        
        Guarantees:
        - Never crashes.
        - Never returns negative numbers.
        - Falls back gracefully to heuristic estimation on extreme or invalid inputs.
        - Respects warehouse physical limits when respect_stock=True.
        """
        clean_event_type = (event_type or "other").strip().lower()
        if clean_event_type not in ("conference", "wedding", "corporate", "birthday", "other"):
            clean_event_type = "other"

        # Determine target date parameters
        if event_date is None:
            event_date = datetime.now(timezone.utc)
        season = self.get_season(event_date)
        day_of_week = event_date.weekday()

        # Check if fallback is required
        # (Negative guests, zero, extreme outliers > 10,000, or missing model)
        use_fallback = (
            expected_guests is None or
            expected_guests <= 0 or
            expected_guests > 10000 or
            self._predictor is None
        )

        if use_fallback:
            items_preds, is_fallback = self._rule_based_fallback(
                clean_event_type, max(0, expected_guests or 0), duration_hours
            )
        else:
            try:
                input_df = pd.DataFrame([{
                    "event_type": clean_event_type,
                    "expected_guests": expected_guests,
                    "duration_hours": float(duration_hours or 4.0),
                    "season": season,
                    "day_of_week": int(day_of_week),
                }])

                raw_preds = self._predictor["pipeline"].predict(input_df)[0]
                target_cols = self._predictor["target_cols"]
                residual_stds = self._predictor.get("residual_stds", {})

                items_preds = {}
                for idx, col in enumerate(target_cols):
                    pred_val = max(0, int(np.round(raw_preds[idx])))
                    std_val = residual_stds.get(col, 2.0)
                    lower = max(0, int(np.floor(pred_val - 1.645 * std_val)))
                    upper = int(np.ceil(pred_val + 1.645 * std_val))
                    items_preds[col] = {
                        "suggested_quantity": pred_val,
                        "confidence_lower": lower,
                        "confidence_upper": upper,
                    }
                is_fallback = False
            except Exception as e:
                print(f"Model prediction error, falling back to heuristics: {e}")
                items_preds, is_fallback = self._rule_based_fallback(
                    clean_event_type, max(0, expected_guests or 0), duration_hours
                )

        # Match predicted target items with actual catalog items in database
        recommendations = self._format_and_constrain_recommendations(
            items_preds=items_preds,
            respect_stock=respect_stock,
            db=db,
        )

        return {
            "event_type": clean_event_type,
            "expected_guests": expected_guests,
            "duration_hours": duration_hours,
            "is_fallback": is_fallback,
            "model_version": self._predictor.get("version", "heuristic") if self._predictor else "heuristic",
            "items": recommendations,
        }

    def _rule_based_fallback(
        self, event_type: str, guests: int, duration_hours: float
    ) -> Tuple[Dict[str, Dict[str, int]], bool]:
        """
        Deterministic, safe heuristic fallback when inputs are out of bounds or model is absent.
        Always non-negative and scales with guest count.
        """
        if guests <= 0:
            return {
                "chairs": {"suggested_quantity": 0, "confidence_lower": 0, "confidence_upper": 0},
                "tables": {"suggested_quantity": 0, "confidence_lower": 0, "confidence_upper": 0},
                "microphones": {"suggested_quantity": 0, "confidence_lower": 0, "confidence_upper": 0},
                "projectors": {"suggested_quantity": 0, "confidence_lower": 0, "confidence_upper": 0},
                "speakers": {"suggested_quantity": 0, "confidence_lower": 0, "confidence_upper": 0},
            }, True

        # 1. Chairs
        multiplier = 1.10 if event_type == "wedding" else 1.05
        chairs = max(guests, int(np.ceil(guests * multiplier)))

        # 2. Tables
        table_ratio = 8.0 if event_type in ("wedding", "birthday") else 6.0
        tables = max(1, int(np.ceil(guests / table_ratio)))

        # 3. Microphones
        if event_type in ("conference", "corporate"):
            mics = max(2, int(2 + guests // 50))
        else:
            mics = max(1, int(1 + guests // 100))

        # 4. Projectors
        projectors = 1 if event_type in ("conference", "corporate") and guests >= 20 else 0

        # 5. Speakers
        speakers = max(2, int(2 + guests // 50))

        results = {
            "chairs": {
                "suggested_quantity": chairs,
                "confidence_lower": max(0, int(chairs * 0.95)),
                "confidence_upper": int(chairs * 1.08),
            },
            "tables": {
                "suggested_quantity": tables,
                "confidence_lower": max(1, int(tables * 0.9)),
                "confidence_upper": int(tables * 1.15),
            },
            "microphones": {
                "suggested_quantity": mics,
                "confidence_lower": max(1, mics - 1),
                "confidence_upper": mics + 1,
            },
            "projectors": {
                "suggested_quantity": projectors,
                "confidence_lower": projectors,
                "confidence_upper": max(projectors, 1 if event_type in ("conference", "corporate") else 0),
            },
            "speakers": {
                "suggested_quantity": speakers,
                "confidence_lower": max(2, speakers - 1),
                "confidence_upper": speakers + 2,
            },
        }
        return results, True

    def _format_and_constrain_recommendations(
        self,
        items_preds: Dict[str, Dict[str, int]],
        respect_stock: bool,
        db: Optional[Session]
    ) -> List[Dict[str, Any]]:
        """
        Formats predictions and optionally enforces warehouse availability bounds.
        """
        # Mapping predicted categories to actual items in DB
        db_items_map = {}
        if db is not None:
            active_items = db.query(InventoryItem).filter(InventoryItem.is_active.is_(True)).all()
            for item in active_items:
                cat_lower = item.category.lower()
                name_lower = item.name.lower()
                if "chair" in name_lower or "chair" in cat_lower or "furniture" in cat_lower:
                    db_items_map.setdefault("chairs", []).append(item)
                elif "table" in name_lower:
                    db_items_map.setdefault("tables", []).append(item)
                elif "mic" in name_lower or ("audio" in cat_lower and "mic" in name_lower):
                    db_items_map.setdefault("microphones", []).append(item)
                elif "projector" in name_lower or "visual" in cat_lower:
                    db_items_map.setdefault("projectors", []).append(item)
                elif "speaker" in name_lower or "audio" in cat_lower:
                    db_items_map.setdefault("speakers", []).append(item)

        results = []
        display_names = {
            "chairs": "Banquet Chairs",
            "tables": "Folding Tables",
            "microphones": "Wireless Microphones",
            "projectors": "HD Projector",
            "speakers": "PA Audio Speakers",
        }
        categories_map = {
            "chairs": "Furniture",
            "tables": "Furniture",
            "microphones": "Audio",
            "projectors": "Visual",
            "speakers": "Audio",
        }

        for target_key, pred_data in items_preds.items():
            suggested = pred_data["suggested_quantity"]
            lower = pred_data["confidence_lower"]
            upper = pred_data["confidence_upper"]

            # Check if matching item exists in database
            matched_item = None
            if target_key in db_items_map and db_items_map[target_key]:
                matched_item = db_items_map[target_key][0]

            item_id = matched_item.id if matched_item else None
            item_name = matched_item.name if matched_item else display_names.get(target_key, target_key.capitalize())
            category = matched_item.category if matched_item else categories_map.get(target_key, "Other")
            available_stock = matched_item.physically_available_base if matched_item else None

            final_suggested = suggested
            is_constrained = False

            # GOLDEN RULE: If respect_stock is requested and stock is lower than ML suggestion
            if respect_stock and available_stock is not None:
                if suggested > available_stock:
                    final_suggested = available_stock
                    is_constrained = True

            results.append({
                "item_key": target_key,
                "item_id": item_id,
                "item_name": item_name,
                "category": category,
                "suggested_quantity": final_suggested,
                "model_raw_quantity": suggested,
                "confidence_lower": lower,
                "confidence_upper": upper,
                "available_in_warehouse": available_stock,
                "is_stock_constrained": is_constrained,
            })

        return results

    def assess_shortage_risk(
        self,
        item_id: int,
        db: Session,
        days_ahead: int = 14
    ) -> Dict[str, Any]:
        """
        Evaluates shortage risk for an item over the upcoming reservation horizon.
        Uses Model 2 (Shortage Classifier) with deterministic safety heuristics fallback.
        """
        item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
        if not item:
            return {
                "item_id": item_id,
                "error": "Item not found",
                "risk_score": 0.0,
                "risk_level": "Low",
                "reason": "Item does not exist"
            }

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        horizon_end = now_utc + timedelta(days=days_ahead)

        current_stock = item.physically_available_base
        threshold = item.minimum_threshold

        # Calculate total confirmed reservation demands over upcoming window
        overlapping_events = (
            db.query(EventItem)
            .join(Event, EventItem.event_id == Event.id)
            .filter(
                EventItem.item_id == item.id,
                Event.status == EventStatus.CONFIRMED,
                Event.start_time < horizon_end,
                Event.end_time > now_utc,
            )
            .all()
        )

        total_reserved = sum(ei.quantity for ei in overlapping_events)
        demand_ratio = round(total_reserved / max(1, current_stock), 3)

        # 1. ML Classifier Prediction
        risk_score = None
        if self._classifier is not None:
            try:
                features_df = pd.DataFrame([{
                    "category": item.category,
                    "current_stock": current_stock,
                    "threshold": threshold,
                    "days_until_event": days_ahead,
                    "total_reserved_next_7d": total_reserved,
                    "demand_ratio": demand_ratio,
                }])
                prob = self._classifier["pipeline"].predict_proba(features_df)[0]
                # Probability of shortage (class 1)
                risk_score = float(round(prob[1], 3))
            except Exception as e:
                print(f"Shortage classifier error, using safety heuristics: {e}")
                risk_score = None

        # 2. Fallback heuristic if ML prediction unavailable
        net_after_demand = current_stock - total_reserved
        if risk_score is None:
            if net_after_demand <= 0:
                risk_score = 0.95
            elif net_after_demand <= threshold:
                risk_score = 0.75
            elif net_after_demand <= (threshold * 1.5):
                risk_score = 0.45
            else:
                risk_score = 0.10

        # Classify risk level
        if risk_score >= 0.70 or net_after_demand <= threshold:
            risk_level = "High"
            reason = (
                f"High risk: upcoming demand ({total_reserved} units) "
                f"depletes available stock ({current_stock}) below safety threshold ({threshold})."
            )
        elif risk_score >= 0.35:
            risk_level = "Medium"
            reason = (
                f"Medium risk: demand buffer is tight ({net_after_demand} remaining vs threshold {threshold})."
            )
        else:
            risk_level = "Low"
            reason = f"Comfortable inventory buffer: {net_after_demand} units remain available."

        return {
            "item_id": item.id,
            "item_name": item.name,
            "category": item.category,
            "current_stock": current_stock,
            "minimum_threshold": threshold,
            "total_reserved_upcoming": total_reserved,
            "net_projected_stock": net_after_demand,
            "demand_ratio": demand_ratio,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "reason": reason,
        }

    def get_all_shortage_risks(
        self,
        db: Session,
        days_ahead: int = 14,
        min_level: str = "medium"
    ) -> List[Dict[str, Any]]:
        """Scans all active catalog items and returns items matching or exceeding min_level."""
        items = db.query(InventoryItem).filter(InventoryItem.is_active.is_(True)).all()
        results = []

        valid_levels = ("medium", "high") if min_level.lower() == "medium" else ("high",)

        for item in items:
            assessment = self.assess_shortage_risk(item.id, db, days_ahead=days_ahead)
            if assessment.get("risk_level", "").lower() in valid_levels:
                results.append(assessment)

        # Sort descending by risk score
        results.sort(key=lambda x: x.get("risk_score", 0.0), reverse=True)
        return results

    def retrain_models(self, db: Session, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Retrains ML models on current database records + synthetic historical samples,
        and logs the training run into model_runs table.
        """
        from ml.train_models import train_all_models

        # Run training
        metadata = train_all_models()
        self.reload()

        m1_metrics = metadata.get("quantity_predictor", {})

        # Count training data samples
        data_path = ML_DIR / "data" / "event_training_data.csv"
        sample_count = 1200
        if data_path.exists():
            try:
                sample_count = len(pd.read_csv(data_path))
            except Exception:
                pass

        # Log into model_runs table
        model_run = ModelRun(
            model_name="RandomForestRegressor + Classifier",
            version=metadata.get("version", "1.0.0"),
            mae=m1_metrics.get("mae"),
            rmse=m1_metrics.get("rmse"),
            r2_score=m1_metrics.get("r2_score"),
            baseline_mae=m1_metrics.get("baseline_mae"),
            is_better_than_baseline=m1_metrics.get("is_better_than_baseline", True),
            training_samples_count=sample_count,
            synthetic_samples_count=sample_count,
            model_file_path=str(self.predictor_path),
            notes=f"Trained on {sample_count} events with 80/20 train/test split.",
        )
        db.add(model_run)
        db.commit()
        db.refresh(model_run)

        return {
            "success": True,
            "model_run": model_run.to_dict(),
            "metadata": metadata,
        }


# Singleton service instance
_ml_service_instance = None


def get_ml_service() -> MLService:
    global _ml_service_instance
    if _ml_service_instance is None:
        _ml_service_instance = MLService()
    return _ml_service_instance
