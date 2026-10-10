"""Verifies ML endpoints on live development server."""

import json
import urllib.request
import http.cookiejar

BASE_URL = "http://127.0.0.1:5000"

def test_ml_live():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    # 1. Login as Organizer
    login_body = json.dumps({"username": "organizer1", "password": "OrganizerPass123!"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}/api/auth/login", data=login_body, headers={"Content-Type": "application/json"})
    with opener.open(req) as r:
        data = json.loads(r.read().decode("utf-8"))
        csrf_token = data.get("csrf_token")
    print(f"[OK] Organizer logged in. CSRF Token: {csrf_token[:8]}...")

    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf_token,
    }

    # 2. Predict Items for 120-attendee Conference
    predict_body = json.dumps({
        "event_type": "conference",
        "expected_guests": 120,
        "duration_hours": 6.0,
        "respect_stock": False
    }).encode("utf-8")

    req = urllib.request.Request(f"{BASE_URL}/api/ml/predict-items", data=predict_body, headers=headers)
    with opener.open(req) as r:
        pred_data = json.loads(r.read().decode("utf-8"))

    print("\n[OK] AI Recommended Inventory for 120-attendee Conference:")
    for item in pred_data.get("items", []):
        print(f"  • {item['item_name']} ({item['category']}): {item['suggested_quantity']} units [90% Range: {item['confidence_lower']} - {item['confidence_upper']}]")

    # 3. Check Shortage Risk Radar
    req = urllib.request.Request(f"{BASE_URL}/api/ml/shortage-risks?days_ahead=14", headers={"Accept": "application/json"})
    with opener.open(req) as r:
        risk_data = json.loads(r.read().decode("utf-8"))

    print(f"\n[OK] Shortage Risk Radar scanned 14-day horizon: {risk_data['risks_count']} items currently flagged at Medium/High risk.")
    for item in risk_data.get("items_at_risk", []):
        print(f"  • {item['item_name']} ({item['risk_level']} Risk - {round(item['risk_score']*100)}%): {item['reason']}")

    print("\nML LIVE ENDPOINTS VERIFIED SUCCESSFULLY!")

if __name__ == "__main__":
    test_ml_live()
