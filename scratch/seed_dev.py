import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import create_app
from backend.models.base import db_session, init_database, create_all_tables
from backend.models.user import User, UserRole
from backend.models.inventory import InventoryItem, InventoryTransaction, ItemType, TransactionType

app = create_app()

with app.app_context():
    # 1. Admin
    admin = db_session.query(User).filter_by(username="admin").first()
    if not admin:
        admin = User(username="admin", email="admin@event.local", role=UserRole.ADMIN, is_active=True)
        admin.set_password("AdminPass123!")
        db_session.add(admin)
        print("Created admin user: admin / AdminPass123!")

    # 2. Organizer
    organizer = db_session.query(User).filter_by(username="organizer1").first()
    if not organizer:
        organizer = User(username="organizer1", email="organizer1@event.local", role=UserRole.ORGANIZER, is_active=True)
        organizer.set_password("OrganizerPass123!")
        db_session.add(organizer)
        print("Created organizer user: organizer1 / OrganizerPass123!")

    db_session.commit()

    # 3. Items
    items_to_seed = [
        {
            "name": "Banquet Chair",
            "category": "Furniture",
            "item_type": ItemType.RETURNABLE,
            "total_stock": 100,
            "unavailable_stock": 0,
            "minimum_threshold": 10,
            "description": "Standard padded banquet chairs"
        },
        {
            "name": "Wireless Microphone",
            "category": "Audio",
            "item_type": ItemType.RETURNABLE,
            "total_stock": 4,
            "unavailable_stock": 0,
            "minimum_threshold": 1,
            "description": "UHF wireless handheld mic"
        },
        {
            "name": "4K Projector",
            "category": "Visual",
            "item_type": ItemType.RETURNABLE,
            "total_stock": 2,
            "unavailable_stock": 0,
            "minimum_threshold": 1,
            "description": "High lumens conference room projector"
        }
    ]

    for item_data in items_to_seed:
        existing = db_session.query(InventoryItem).filter_by(name=item_data["name"]).first()
        if not existing:
            item = InventoryItem(**item_data, unit="pieces", is_active=True)
            db_session.add(item)
            db_session.flush()

            tx = InventoryTransaction(
                item_id=item.id,
                user_id=admin.id,
                change_amount=item.total_stock,
                previous_total_stock=0,
                new_total_stock=item.total_stock,
                transaction_type=TransactionType.INITIAL,
                reason="Initial seed catalog",
            )
            db_session.add(tx)
            print(f"Created seed item: {item.name}")

    db_session.commit()
    print("Seed complete successfully.")
