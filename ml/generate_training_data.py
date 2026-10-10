"""
Synthetic Training Data Generator for Event Inventory Machine Learning Models.
Generates realistic event inventory demands reflecting domain business rules.
"""

import os
import random
import numpy as np
import pandas as pd
from pathlib import Path

# Fix random seed for reproducible synthetic data generation
np.random.seed(42)
random.seed(42)

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def generate_quantity_prediction_data(num_samples: int = 1200) -> pd.DataFrame:
    """
    Generates realistic event inventory dataset.
    Features: event_type, expected_guests, duration_hours, season, day_of_week
    Targets: chairs, tables, microphones, projectors, speakers
    """
    event_types = ["conference", "wedding", "corporate", "birthday", "other"]
    seasons = ["spring", "summer", "fall", "winter"]

    records = []

    for _ in range(num_samples):
        event_type = random.choice(event_types)
        season = random.choice(seasons)
        day_of_week = random.randint(0, 6)

        # Expected guest distribution by event type
        if event_type == "conference":
            expected_guests = int(np.random.choice([30, 50, 100, 150, 200, 300, 400])) + random.randint(-5, 10)
            duration_hours = random.choice([4.0, 6.0, 8.0, 9.0])
        elif event_type == "wedding":
            expected_guests = int(np.random.choice([60, 80, 120, 180, 250])) + random.randint(-5, 15)
            duration_hours = random.choice([5.0, 6.0, 7.0, 8.0])
        elif event_type == "corporate":
            expected_guests = int(np.random.choice([20, 40, 75, 120, 180])) + random.randint(-3, 8)
            duration_hours = random.choice([3.0, 4.0, 5.0, 7.0])
        elif event_type == "birthday":
            expected_guests = int(np.random.choice([15, 25, 40, 60])) + random.randint(-2, 5)
            duration_hours = random.choice([3.0, 4.0, 5.0])
        else:
            expected_guests = int(np.random.choice([25, 50, 100])) + random.randint(-5, 5)
            duration_hours = random.choice([3.0, 4.0, 6.0])

        expected_guests = max(10, expected_guests)

        # 1. Chairs
        if event_type == "wedding":
            chairs = int(np.ceil(expected_guests * 1.10) + np.random.normal(0, 2))
        elif event_type == "conference":
            chairs = int(np.ceil(expected_guests * 1.05) + np.random.normal(0, 2))
        elif event_type == "corporate":
            chairs = int(np.ceil(expected_guests * 1.04) + np.random.normal(0, 1))
        elif event_type == "birthday":
            chairs = int(np.ceil(expected_guests * 1.02) + np.random.normal(0, 1))
        else:
            chairs = int(np.ceil(expected_guests * 1.05) + np.random.normal(0, 2))
        chairs = max(expected_guests, chairs)

        # 2. Tables
        if event_type == "wedding" or event_type == "birthday":
            tables = int(np.ceil(expected_guests / 8.0) + np.random.choice([0, 1]))
        elif event_type == "conference":
            tables = int(np.ceil(expected_guests / 4.0) + np.random.choice([1, 2]))
        elif event_type == "corporate":
            tables = int(np.ceil(expected_guests / 6.0) + np.random.choice([0, 1]))
        else:
            tables = int(np.ceil(expected_guests / 6.0))
        tables = max(2, tables)

        # 3. Microphones
        if event_type == "conference":
            mics = int(2 + (expected_guests // 60) + np.random.choice([0, 1]))
        elif event_type == "corporate":
            mics = int(2 + (expected_guests // 80))
        elif event_type == "wedding":
            mics = int(2 + (1 if expected_guests > 100 else 0))
        elif event_type == "birthday":
            mics = int(1 + (1 if expected_guests > 50 else 0))
        else:
            mics = int(1 + (expected_guests // 100))
        mics = max(1, min(10, mics))

        # 4. Projectors
        if event_type in ("conference", "corporate"):
            projectors = 2 if expected_guests > 150 else 1
        elif event_type in ("wedding", "birthday"):
            projectors = 1 if (expected_guests > 80 and random.random() < 0.6) else 0
        else:
            projectors = 1 if expected_guests > 75 else 0

        # 5. Speakers / Audio
        if event_type in ("wedding", "concert"):
            speakers = int(2 + (expected_guests // 40) * 2)
        elif event_type in ("conference", "corporate"):
            speakers = int(2 + (expected_guests // 75) * 2)
        else:
            speakers = int(2 + (expected_guests // 80))
        speakers = max(2, min(12, speakers))

        records.append({
            "event_type": event_type,
            "expected_guests": expected_guests,
            "duration_hours": duration_hours,
            "season": season,
            "day_of_week": day_of_week,
            "chairs": chairs,
            "tables": tables,
            "microphones": mics,
            "projectors": projectors,
            "speakers": speakers,
        })

    df = pd.DataFrame(records)
    csv_path = DATA_DIR / "event_training_data.csv"
    df.to_csv(csv_path, index=False)
    print(f"Generated {len(df)} item prediction samples -> {csv_path}")
    return df


def generate_shortage_classification_data(num_samples: int = 1000) -> pd.DataFrame:
    """
    Generates dataset for training shortage risk classifier.
    Features: current_stock, threshold, days_until_event, total_reserved_next_7d, demand_ratio
    Target: is_shortage (0 = Low Risk, 1 = High/Medium Risk)
    """
    records = []
    categories = ["Furniture", "Audio", "Visual", "Lighting", "Decor"]

    for _ in range(num_samples):
        cat = random.choice(categories)
        current_stock = random.randint(5, 150)
        threshold = random.randint(2, max(3, current_stock // 5))
        days_until_event = random.randint(1, 30)

        # Simulate upcoming reservation demand
        demand_factor = np.random.exponential(scale=0.7)
        total_reserved = int(current_stock * demand_factor)

        # Available cushion before safety buffer breached
        net_stock = current_stock - total_reserved
        is_shortage = 1 if (net_stock <= threshold) else 0

        demand_ratio = round(total_reserved / max(1, current_stock), 3)

        records.append({
            "category": cat,
            "current_stock": current_stock,
            "threshold": threshold,
            "days_until_event": days_until_event,
            "total_reserved_next_7d": total_reserved,
            "demand_ratio": demand_ratio,
            "is_shortage": is_shortage,
        })

    df = pd.DataFrame(records)
    csv_path = DATA_DIR / "shortage_training_data.csv"
    df.to_csv(csv_path, index=False)
    print(f"Generated {len(df)} shortage risk samples -> {csv_path}")
    return df


if __name__ == "__main__":
    generate_quantity_prediction_data()
    generate_shortage_classification_data()
