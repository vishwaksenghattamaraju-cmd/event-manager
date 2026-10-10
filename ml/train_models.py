"""
Model Training Engine for Event Inventory Machine Learning Layer.
Trains:
1. Item Quantity Predictor (Multi-output RandomForestRegressor)
2. Shortage Risk Classifier (RandomForestClassifier)
Evaluates against baseline models and saves joblib artifacts and metadata.
"""

import sys
from pathlib import Path

# Ensure root directory is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone
import joblib

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, accuracy_score, f1_score

from ml.generate_training_data import generate_quantity_prediction_data, generate_shortage_classification_data

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def train_quantity_predictor():
    """
    Trains Model 1: Item Quantity Predictor.
    Predicts required quantities for core inventory items (Chairs, Tables, Microphones, Projectors, Speakers).
    """
    data_path = DATA_DIR / "event_training_data.csv"
    if not data_path.exists():
        df = generate_quantity_prediction_data()
    else:
        df = pd.read_csv(data_path)

    feature_cols = ["event_type", "expected_guests", "duration_hours", "season", "day_of_week"]
    target_cols = ["chairs", "tables", "microphones", "projectors", "speakers"]

    X = df[feature_cols]
    y = df[target_cols]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Preprocessing
    categorical_features = ["event_type", "season"]
    numeric_features = ["expected_guests", "duration_hours", "day_of_week"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features),
            ("num", "passthrough", numeric_features),
        ]
    )

    # Multi-output Random Forest Regressor
    regressor = RandomForestRegressor(
        n_estimators=100,
        max_depth=12,
        min_samples_split=4,
        random_state=42,
        n_jobs=-1
    )

    pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("regressor", regressor)
    ])

    pipeline.fit(X_train, y_train)

    # Evaluation on test set
    y_pred = pipeline.predict(X_test)
    y_test_np = y_test.values

    # Baseline: Median per event_type
    baseline_preds = []
    medians_by_type = df.groupby("event_type")[target_cols].median()
    for _, row in X_test.iterrows():
        etype = row["event_type"]
        if etype in medians_by_type.index:
            baseline_preds.append(medians_by_type.loc[etype].values)
        else:
            baseline_preds.append(df[target_cols].median().values)
    baseline_preds = np.array(baseline_preds)
    baseline_mae = float(mean_absolute_error(y_test_np, baseline_preds))

    mae = float(mean_absolute_error(y_test_np, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_test_np, y_pred)))
    r2 = float(r2_score(y_test_np, y_pred))

    # Calculate residual standard deviation for prediction intervals (90% confidence = +-1.645 * std)
    residuals = y_test_np - y_pred
    residual_stds = {
        col: float(np.std(residuals[:, i]))
        for i, col in enumerate(target_cols)
    }

    model_artifact = {
        "pipeline": pipeline,
        "feature_cols": feature_cols,
        "target_cols": target_cols,
        "residual_stds": residual_stds,
        "version": "1.0.0",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "r2_score": round(r2, 4),
            "baseline_mae": round(baseline_mae, 4),
            "is_better_than_baseline": mae < baseline_mae,
        }
    }

    model_path = MODELS_DIR / "quantity_predictor.joblib"
    joblib.dump(model_artifact, model_path)
    print(f"[Model 1] Quantity Predictor trained successfully: MAE={mae:.3f} (Baseline={baseline_mae:.3f}), R²={r2:.3f}")
    return model_artifact


def train_shortage_classifier():
    """
    Trains Model 2: Shortage Risk Classifier.
    Predicts shortage risk probability for an item over an upcoming reservation window.
    """
    data_path = DATA_DIR / "shortage_training_data.csv"
    if not data_path.exists():
        df = generate_shortage_classification_data()
    else:
        df = pd.read_csv(data_path)

    feature_cols = ["category", "current_stock", "threshold", "days_until_event", "total_reserved_next_7d", "demand_ratio"]
    target_col = "is_shortage"

    X = df[feature_cols]
    y = df[target_col]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["category"]),
            ("num", StandardScaler(), ["current_stock", "threshold", "days_until_event", "total_reserved_next_7d", "demand_ratio"]),
        ]
    )

    classifier = RandomForestClassifier(
        n_estimators=100,
        max_depth=8,
        min_samples_split=4,
        random_state=42,
        n_jobs=-1
    )

    pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", classifier)
    ])

    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    accuracy = float(accuracy_score(y_test, y_pred))
    f1 = float(f1_score(y_test, y_pred, average="weighted"))

    model_artifact = {
        "pipeline": pipeline,
        "feature_cols": feature_cols,
        "version": "1.0.0",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "accuracy": round(accuracy, 4),
            "f1_score": round(f1, 4),
        }
    }

    model_path = MODELS_DIR / "shortage_classifier.joblib"
    joblib.dump(model_artifact, model_path)
    print(f"[Model 2] Shortage Risk Classifier trained successfully: Accuracy={accuracy:.3f}, F1={f1:.3f}")
    return model_artifact


def train_all_models():
    """Executes full model training pipeline and writes metadata summary."""
    m1 = train_quantity_predictor()
    m2 = train_shortage_classifier()

    metadata = {
        "version": "1.0.0",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "quantity_predictor": m1["metrics"],
        "shortage_classifier": m2["metrics"],
    }

    metadata_path = MODELS_DIR / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"ML artifacts and metadata written to {MODELS_DIR}")
    return metadata


if __name__ == "__main__":
    train_all_models()
