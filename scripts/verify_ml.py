import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from datetime import datetime, timezone
from backend.services.ml_service import get_ml_service
from backend.models.base import init_database, db_session
from backend.config import Config

init_database(Config.DATABASE_URL)
ml = get_ml_service()

print("ML Service loaded.")
print(f"Predictor loaded: {ml._predictor is not None}")
print(f"Classifier loaded: {ml._classifier is not None}")
import json
if ml.metadata_path.exists():
    with open(ml.metadata_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)
        print(f"Metadata: R2={meta.get('quantity_predictor', {}).get('r2_score')}, MAE={meta.get('quantity_predictor', {}).get('mae')}")

# Test 1: Normal prediction
print("\n--- Test 1: Normal input (conference, 120 guests, 6h) ---")
res1 = ml.predict_quantities("conference", 120, 6.0, db=db_session)
print(f"Fallback: {res1['is_fallback']}, Items count: {len(res1['items'])}")
for it in res1['items']:
    print(f"  {it['item_name']} (ID: {it['item_id']}, Cat: {it['category']}): {it['suggested_quantity']} (90% CI: [{it['confidence_lower']}, {it['confidence_upper']}])")

# Test 2: Negative attendees
print("\n--- Test 2: Negative attendees (-25) ---")
res2 = ml.predict_quantities("corporate", -25, 4.0, db=db_session)
print(f"Fallback: {res2['is_fallback']}")
for it in res2['items']:
    print(f"  {it['item_name']}: {it['suggested_quantity']}")
    assert it['suggested_quantity'] >= 0

# Test 3: Zero attendees
print("\n--- Test 3: Zero attendees (0) ---")
res3 = ml.predict_quantities("wedding", 0, 4.0, db=db_session)
print(f"Fallback: {res3['is_fallback']}")
for it in res3['items']:
    print(f"  {it['item_name']}: {it['suggested_quantity']}")
    assert it['suggested_quantity'] == 0

# Test 4: Extreme attendees (50,000)
print("\n--- Test 4: Extreme attendees (50,000) ---")
res4 = ml.predict_quantities("festival", 50000, 8.0, db=db_session)
print(f"Fallback: {res4['is_fallback']}")
for it in res4['items']:
    print(f"  {it['item_name']}: {it['suggested_quantity']}")
    assert it['suggested_quantity'] >= 0

# Test 5: Missing / None inputs
print("\n--- Test 5: Missing / None inputs ---")
res5 = ml.predict_quantities(None, None, None, db=db_session)
print(f"Fallback: {res5['is_fallback']}")
for it in res5['items']:
    print(f"  {it['item_name']}: {it['suggested_quantity']}")
    assert it['suggested_quantity'] >= 0

# Test 6: Shortage risk assessment
print("\n--- Test 6: Shortage risk assessment ---")
all_risks = ml.get_all_shortage_risks(db_session)
print(f"Shortage risk items evaluated: {len(all_risks)}")
for r in all_risks[:3]:
    print(f"  {r['item_name']}: risk_level={r['risk_level']}, score={r['risk_score']}")
