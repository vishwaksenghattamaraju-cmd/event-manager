"""End-to-end verification of the exact HTTP flow executed by the frontend JavaScript using standard library urllib."""

import json
import urllib.request
import urllib.error
import http.cookiejar

BASE_URL = "http://127.0.0.1:5000"

def make_request(opener, url, method="GET", data=None, headers=None):
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    
    encoded_data = None
    if data is not None:
        encoded_data = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    
    req = urllib.request.Request(url, data=encoded_data, headers=hdrs, method=method)
    try:
        with opener.open(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, body

def run_verification():
    # Cookie jar to hold session cookies
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    print("1. Fetching login page HTML...")
    status, body = make_request(opener, f"{BASE_URL}/login")
    assert status == 200, f"Login page failed with status {status}"
    assert "Event Inventory System" in body
    print("   [OK] Login page HTML served successfully.")

    print("2. Admin login...")
    status, body = make_request(opener, f"{BASE_URL}/api/auth/login", method="POST", data={"username": "admin", "password": "AdminPass123!"})
    assert status == 200, f"Login failed: {body}"
    login_data = json.loads(body)
    csrf_token = login_data.get("csrf_token")
    headers = {"X-CSRF-Token": csrf_token}
    print(f"   [OK] Logged in as admin. CSRF token acquired: {csrf_token[:8]}...")

    print("3. Admin adds new inventory item 'Stage Spotlight'...")
    status, body = make_request(opener, f"{BASE_URL}/api/inventory", method="POST", headers=headers, data={
        "sku": "LGT-SPOT-01",
        "category": "Lighting",
        "name": "Stage Spotlight",
        "total_stock": 5,
        "minimum_threshold": 2,
        "is_consumable": False
    })
    if status == 400 and "already exists" in body:
        print("   [OK] Stage Spotlight already exists in catalog.")
    else:
        assert status == 201, f"Create item failed: {body}"
        print("   [OK] Stage Spotlight created with 5 units.")

    print("4. Fetching Dashboard Summary as Admin...")
    status, body = make_request(opener, f"{BASE_URL}/api/reports/dashboard-summary", method="GET")
    assert status == 200
    summary = json.loads(body)
    print(f"   [OK] Dashboard summary: {summary['inventory']['total_items_count']} catalog items, {summary['inventory']['total_physical_stock']} units.")

    print("5. Logging out admin...")
    status, body = make_request(opener, f"{BASE_URL}/api/auth/logout", method="POST", headers=headers)
    assert status == 200
    print("   [OK] Admin logged out.")

    print("6. Organizer login...")
    org_cj = http.cookiejar.CookieJar()
    org_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(org_cj))
    status, body = make_request(org_opener, f"{BASE_URL}/api/auth/login", method="POST", data={"username": "organizer1", "password": "OrganizerPass123!"})
    assert status == 200, f"Organizer login failed: {body}"
    org_csrf = json.loads(body).get("csrf_token")
    org_headers = {"X-CSRF-Token": org_csrf}
    print("   [OK] Organizer logged in.")

    print("7. Getting item ID for 'Stage Spotlight'...")
    status, body = make_request(org_opener, f"{BASE_URL}/api/inventory", method="GET")
    assert status == 200
    items = json.loads(body).get("items", [])
    spotlight = next((i for i in items if i["name"] == "Stage Spotlight"), None)
    assert spotlight is not None, "Spotlight not found in catalog"
    item_id = spotlight["id"]

    print("8. Testing live availability check with SHORTAGE (requesting 10 units when only 5 exist)...")
    status, body = make_request(org_opener, f"{BASE_URL}/api/events/check-availability", method="POST", headers=org_headers, data={
        "start_time": "2026-11-01T10:00:00",
        "end_time": "2026-11-01T18:00:00",
        "items": [{"item_id": item_id, "quantity": 10}]
    })
    assert status == 200, f"Check availability failed with {status}: {body}"
    avail_data = json.loads(body)
    assert avail_data["is_sufficient"] is False, "Expected shortage but got sufficient"
    assert len(avail_data["shortages"]) > 0
    shortage_info = avail_data["shortages"][0]
    print(f"   [OK] Live check correctly flagged shortage: requested {shortage_info['requested']}, available {shortage_info['available']}, deficit -{shortage_info['short_by']}.")

    print("9. Testing live availability check with SUFFICIENT stock (requesting 2 units)...")
    status, body = make_request(org_opener, f"{BASE_URL}/api/events/check-availability", method="POST", headers=org_headers, data={
        "start_time": "2026-11-01T10:00:00",
        "end_time": "2026-11-01T18:00:00",
        "items": [{"item_id": item_id, "quantity": 2}]
    })
    assert status == 200, f"Check availability failed with {status}: {body}"
    avail_data = json.loads(body)
    assert avail_data["is_sufficient"] is True
    print("   [OK] Live check correctly confirmed stock is sufficient.")

    print("10. Confirming booking for 2 units...")
    status, body = make_request(org_opener, f"{BASE_URL}/api/events", method="POST", headers=org_headers, data={
        "title": "Annual Music Showcase",
        "event_type": "concert",
        "expected_attendees": 80,
        "start_time": "2026-11-01T10:00:00",
        "end_time": "2026-11-01T18:00:00",
        "status": "CONFIRMED",
        "items": [{"item_id": item_id, "quantity": 2}]
    })
    assert status == 201, f"Booking failed with status {status}: {body}"
    event_obj = json.loads(body)["event"]
    assert event_obj["status"] == "confirmed"
    print(f"   [OK] Event '{event_obj['name']}' booked and confirmed successfully (Event ID: {event_obj['id']})!")

    print("\nALL 10 FRONTEND WORKFLOW STEPS VERIFIED END-TO-END!")

if __name__ == "__main__":
    run_verification()
