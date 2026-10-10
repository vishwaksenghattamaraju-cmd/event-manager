"""
Database Seed Script: Populates realistic event inventory, user accounts, bookings, and alerts.
Run with: python scripts/seed_demo_data.py
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Enable utf-8 on Windows terminal if supported
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure root workspace is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.config import Config
from backend.models.base import init_database, create_all_tables, db_session
from backend.models.user import User, UserRole
from backend.models.inventory import InventoryItem, InventoryTransaction, ItemType, TransactionType
from backend.models.event import Event, EventItem, EventStatus, EventType
from backend.services.inventory_service import create_item
from backend.services.booking_service import confirm_event_booking, complete_event
from backend.services.alert_service import scan_all_inventory_and_generate_alerts


def seed():
    print("[*] Initializing Database Seeding...")
    init_database(Config.DATABASE_URL)
    create_all_tables()

    # 1. Seed Users
    admin = db_session.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@eventinventory.local",
            role=UserRole.ADMIN,
            is_active=True,
        )
        admin.set_password("AdminSecure123!")
        db_session.add(admin)
        print("  [+] Created Admin: admin / AdminSecure123!")

    organizer = db_session.query(User).filter(User.username == "organizer").first()
    if not organizer:
        organizer = User(
            username="organizer",
            email="organizer@eventinventory.local",
            role=UserRole.ORGANIZER,
            is_active=True,
        )
        organizer.set_password("OrganizerPass123!")
        db_session.add(organizer)
        print("  [+] Created Organizer: organizer / OrganizerPass123!")

    db_session.commit()
    db_session.refresh(admin)
    db_session.refresh(organizer)

    # 2. Seed Catalog Items
    catalog_specs = [
        # Audio
        {"name": "1000W Active PA Speaker", "category": "Audio", "item_type": "returnable", "total_stock": 24, "unavailable_stock": 0, "minimum_threshold": 4, "unit": "units", "purchase_cost": 350.0},
        {"name": "Wireless Handheld Microphone", "category": "Audio", "item_type": "returnable", "total_stock": 25, "unavailable_stock": 2, "minimum_threshold": 5, "unit": "mics", "purchase_cost": 120.0},
        {"name": "16-Channel Audio Mixer Console", "category": "Audio", "item_type": "returnable", "total_stock": 6, "unavailable_stock": 0, "minimum_threshold": 2, "unit": "consoles", "purchase_cost": 480.0},
        # Visual
        {"name": "4K Laser Projector 6000L", "category": "Visual", "item_type": "returnable", "total_stock": 8, "unavailable_stock": 1, "minimum_threshold": 2, "unit": "projectors", "purchase_cost": 1200.0},
        {"name": "120\" Portable Motorized Screen", "category": "Visual", "item_type": "returnable", "total_stock": 10, "unavailable_stock": 0, "minimum_threshold": 2, "unit": "screens", "purchase_cost": 280.0},
        {"name": "65\" 4K Commercial Display & Stand", "category": "Visual", "item_type": "returnable", "total_stock": 12, "unavailable_stock": 0, "minimum_threshold": 3, "unit": "displays", "purchase_cost": 650.0},
        # Lighting
        {"name": "RGBW Stage Uplight Par", "category": "Lighting", "item_type": "returnable", "total_stock": 60, "unavailable_stock": 4, "minimum_threshold": 12, "unit": "lights", "purchase_cost": 45.0},
        {"name": "Moving Head Beam Spotlight", "category": "Lighting", "item_type": "returnable", "total_stock": 16, "unavailable_stock": 0, "minimum_threshold": 4, "unit": "fixtures", "purchase_cost": 320.0},
        # Furniture
        {"name": "Deluxe Padded Banquet Chair", "category": "Furniture", "item_type": "returnable", "total_stock": 350, "unavailable_stock": 10, "minimum_threshold": 50, "unit": "chairs", "purchase_cost": 35.0},
        {"name": "60\" Round Banquet Table (Seats 8)", "category": "Furniture", "item_type": "returnable", "total_stock": 45, "unavailable_stock": 2, "minimum_threshold": 8, "unit": "tables", "purchase_cost": 95.0},
        {"name": "6ft Rectangular Catering Table", "category": "Furniture", "item_type": "returnable", "total_stock": 30, "unavailable_stock": 0, "minimum_threshold": 5, "unit": "tables", "purchase_cost": 75.0},
        {"name": "Cocktail High-Boy Bistro Table", "category": "Furniture", "item_type": "returnable", "total_stock": 25, "unavailable_stock": 0, "minimum_threshold": 5, "unit": "tables", "purchase_cost": 55.0},
        # Decor
        {"name": "Pipe & Drape Velvet Backdrop (10ft)", "category": "Decor", "item_type": "returnable", "total_stock": 15, "unavailable_stock": 0, "minimum_threshold": 3, "unit": "sets", "purchase_cost": 180.0},
        {"name": "Acrylic Presidential Lectern", "category": "Decor", "item_type": "returnable", "total_stock": 5, "unavailable_stock": 0, "minimum_threshold": 1, "unit": "podiums", "purchase_cost": 220.0},
        # Consumables
        {"name": "Premium Satin Napkins (Pack of 50)", "category": "Consumables", "item_type": "consumable", "total_stock": 70, "unavailable_stock": 0, "minimum_threshold": 15, "unit": "packs", "purchase_cost": 18.0},
        {"name": "Biodegradable Party Confetti Cannon", "category": "Consumables", "item_type": "consumable", "total_stock": 35, "unavailable_stock": 0, "minimum_threshold": 10, "unit": "cannons", "purchase_cost": 8.0},
        {"name": "Silicone Security Wristbands (100pk)", "category": "Consumables", "item_type": "consumable", "total_stock": 15, "unavailable_stock": 0, "minimum_threshold": 5, "unit": "packs", "purchase_cost": 12.0},
    ]

    items_map = {}
    for spec in catalog_specs:
        existing = db_session.query(InventoryItem).filter(InventoryItem.name == spec["name"]).first()
        if not existing:
            item, err = create_item(db_session, spec, user_id=admin.id)
            if err:
                print(f"  [-] Error creating {spec['name']}: {err}")
            else:
                items_map[item.name] = item
                print(f"  [+] Added Item: {item.name} ({item.sku}) [{item.total_stock} {item.unit}]")
        else:
            items_map[existing.name] = existing

    # 3. Seed Sample Events
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Event 1: Completed Annual Gala (in the past)
    ev1_name = "Global Leadership Gala 2026"
    ev1 = db_session.query(Event).filter(Event.name == ev1_name).first()
    if not ev1:
        ev1 = Event(
            name=ev1_name,
            event_type=EventType.CORPORATE,
            status=EventStatus.CONFIRMED,
            start_time=now - timedelta(days=5, hours=6),
            end_time=now - timedelta(days=5),
            expected_guest_count=180,
            location="Metropolitan Grand Ballroom",
            organizer_id=organizer.id,
        )
        db_session.add(ev1)
        db_session.flush()

        chair_item = items_map.get("Deluxe Padded Banquet Chair")
        table_item = items_map.get("60\" Round Banquet Table (Seats 8)")
        confetti_item = items_map.get("Biodegradable Party Confetti Cannon")

        if chair_item:
            db_session.add(EventItem(event_id=ev1.id, item_id=chair_item.id, quantity=180))
        if table_item:
            db_session.add(EventItem(event_id=ev1.id, item_id=table_item.id, quantity=24))
        if confetti_item:
            db_session.add(EventItem(event_id=ev1.id, item_id=confetti_item.id, quantity=10))

        db_session.commit()
        # Mark as completed (consumes confetti)
        complete_event(db_session, ev1.id, user_id=organizer.id)
        print(f"  [+] Seeded Completed Event: '{ev1.name}' (consumed items deducted)")

    # Event 2: Confirmed Upcoming Tech Summit
    ev2_name = "NextGen AI Summit 2026"
    ev2 = db_session.query(Event).filter(Event.name == ev2_name).first()
    if not ev2:
        ev2 = Event(
            name=ev2_name,
            event_type=EventType.CONFERENCE,
            status=EventStatus.DRAFT,
            start_time=now + timedelta(days=3, hours=9),
            end_time=now + timedelta(days=3, hours=17),
            expected_guest_count=120,
            location="Innovation Convention Center, Hall B",
            organizer_id=organizer.id,
        )
        db_session.add(ev2)
        db_session.flush()

        speaker_item = items_map.get("1000W Active PA Speaker")
        mic_item = items_map.get("Wireless Handheld Microphone")
        projector_item = items_map.get("4K Laser Projector 6000L")
        chair_item = items_map.get("Deluxe Padded Banquet Chair")

        if speaker_item:
            db_session.add(EventItem(event_id=ev2.id, item_id=speaker_item.id, quantity=8))
        if mic_item:
            db_session.add(EventItem(event_id=ev2.id, item_id=mic_item.id, quantity=6))
        if projector_item:
            db_session.add(EventItem(event_id=ev2.id, item_id=projector_item.id, quantity=2))
        if chair_item:
            db_session.add(EventItem(event_id=ev2.id, item_id=chair_item.id, quantity=120))

        db_session.commit()
        confirm_event_booking(db_session, ev2.id, user_id=organizer.id)
        print(f"  [+] Seeded Confirmed Upcoming Event: '{ev2.name}'")

    # Event 3: Draft Wedding Reception
    ev3_name = "Sarah & Marcus Wedding Celebration"
    ev3 = db_session.query(Event).filter(Event.name == ev3_name).first()
    if not ev3:
        ev3 = Event(
            name=ev3_name,
            event_type=EventType.WEDDING,
            status=EventStatus.DRAFT,
            start_time=now + timedelta(days=8, hours=14),
            end_time=now + timedelta(days=8, hours=23),
            expected_guest_count=100,
            location="Pinecrest Garden Pavilion",
            organizer_id=organizer.id,
        )
        db_session.add(ev3)
        db_session.flush()

        uplight_item = items_map.get("RGBW Stage Uplight Par")
        chair_item = items_map.get("Deluxe Padded Banquet Chair")
        table_item = items_map.get("60\" Round Banquet Table (Seats 8)")

        if uplight_item:
            db_session.add(EventItem(event_id=ev3.id, item_id=uplight_item.id, quantity=24))
        if chair_item:
            db_session.add(EventItem(event_id=ev3.id, item_id=chair_item.id, quantity=100))
        if table_item:
            db_session.add(EventItem(event_id=ev3.id, item_id=table_item.id, quantity=14))

        db_session.commit()
        print(f"  [+] Seeded Draft Event: '{ev3.name}'")

    # 4. Trigger realistic low stock scenario to demonstrate the alert engine
    from backend.services.inventory_service import adjust_stock
    mic = db_session.query(InventoryItem).filter(InventoryItem.name.like("%Microphone%")).first()
    if mic and mic.physically_available_base > mic.minimum_threshold:
        diff = mic.total_stock - 3  # bring stock down to 3 (below threshold of 5)
        adjust_stock(db_session, mic.id, -diff, "Dispatched backup mics to regional satellite warehouse", user_id=admin.id)
        print(f"  [!] Adjusted '{mic.name}' to 3 units (threshold: {mic.minimum_threshold}) to demonstrate alerts.")

    # 5. Trigger alert scan
    print("[*] Scanning inventory and generating initial alerts...")
    alerts = scan_all_inventory_and_generate_alerts(db_session)
    print(f"  [+] Generated {len(alerts)} active alerts.")

    print("\n[SUCCESS] Seeding Complete!")
    print("-------------------------------------------------------")
    print("  Administrator Credentials : admin / AdminSecure123!")
    print("  Organizer Credentials     : organizer / OrganizerPass123!")
    print("  Web Server URL            : http://127.0.0.1:5000")
    print("-------------------------------------------------------")


if __name__ == "__main__":
    seed()
