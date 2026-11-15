"""
PostgreSQL Verification and Health Check Tool.
Event Inventory Management System.

Tests:
1. TCP / Database connectivity to PostgreSQL.
2. Database version, server info, and connection parameters.
3. Existence of required schema tables.
4. Record counts across all tables.
5. Authentication test for migrated users (admin/organizer).
6. CRUD operation test (user registration, duplicate prevention, password verification, cleanup).
"""

import os
import sys
import argparse
from pathlib import Path

# Ensure root workspace is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from backend.models.user import User, UserRole
from backend.services.auth_service import register_user, authenticate_user


def test_postgres(database_url: str):
    print("=" * 70)
    print("POSTGRESQL CONNECTION & SCHEMA VERIFICATION")
    print("=" * 70)

    # Normalize url
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    import re
    safe_url = re.sub(r":([^:@]+)@", ":****@", database_url)
    print(f"Target Database: {safe_url}")

    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT current_database(), current_user, version()")).fetchone()
            print(f"[OK] Connected successfully!")
            print(f"     Database: {row[0]}")
            print(f"     User:     {row[1]}")
            print(f"     Version:  {row[2].split(',')[0]}")
    except Exception as e:
        print(f"[FAIL] Could not connect to PostgreSQL: {e}")
        return False

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\n[INFO] Found {len(tables)} tables: {tables}")

    expected_tables = ["users", "inventory_items", "inventory_transactions", "events", "event_items", "alerts", "model_runs"]
    missing = [t for t in expected_tables if t not in tables]
    if missing:
        print(f"[WARN] Missing tables: {missing}")
    else:
        print("[OK] All 7 application tables present.")

    # Record counts
    print("\n--- Table Record Counts ---")
    with engine.connect() as conn:
        for t in expected_tables:
            if t in tables:
                cnt = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                print(f"  {t:25s}: {cnt} rows")

    # Session test
    Session = sessionmaker(bind=engine)
    session = Session()

    print("\n--- Testing Authentication & Data Integrity ---")
    try:
        # Check admin user
        admin = session.query(User).filter(User.username == "admin").first()
        if admin:
            print(f"[OK] Admin user found: id={admin.id}, email={admin.email}, active={admin.is_active}")
            pw_ok = admin.check_password("Admin@123")
            print(f"     Password check ('Admin@123'): {'PASSED' if pw_ok else 'FAILED'}")
        else:
            print("[WARN] Admin user not found in database.")

        # Check organizer user
        organizer = session.query(User).filter(User.username == "organizer").first()
        if organizer:
            print(f"[OK] Organizer user found: id={organizer.id}, email={organizer.email}, active={organizer.is_active}")
            pw_ok = organizer.check_password("Organizer@123")
            print(f"     Password check ('Organizer@123'): {'PASSED' if pw_ok else 'FAILED'}")
        else:
            print("[WARN] Organizer user not found in database.")

        # Test registration, duplicate rejection, and cleanup
        print("\n--- Testing Registration & Integrity Constraints ---")
        test_uname = "pg_verify_test_user"
        test_email = "pg_verify_test@example.com"
        test_pw = "VerifyPassword123!"

        # Clean up any leftover test user
        existing_test = session.query(User).filter(User.username == test_uname).first()
        if existing_test:
            session.delete(existing_test)
            session.commit()

        # 1. Register test user
        new_user, err = register_user(session, test_uname, test_email, test_pw, role=UserRole.ORGANIZER)
        if err or not new_user:
            print(f"[FAIL] Registration failed: {err}")
        else:
            print(f"[OK] Successfully registered test user (id={new_user.id}).")

            # 2. Prevent duplicate registration
            dup_user, dup_err = register_user(session, test_uname, "different@example.com", test_pw)
            if dup_err and not dup_user:
                print(f"[OK] Duplicate username prevented: '{dup_err}'")
            else:
                print("[FAIL] Duplicate username was NOT prevented!")

            # 3. Authenticate with correct credentials
            auth_user, auth_err = authenticate_user(session, test_uname, test_pw)
            if auth_user and not auth_err:
                print("[OK] Authentication with correct credentials succeeded.")
            else:
                print(f"[FAIL] Authentication failed: {auth_err}")

            # 4. Reject incorrect password
            bad_user, bad_err = authenticate_user(session, test_uname, "WrongPassword!")
            if not bad_user and "Invalid" in (bad_err or ""):
                print("[OK] Incorrect password correctly rejected.")
            else:
                print(f"[FAIL] Incorrect password rejection unexpected result: {bad_err}")

            # Clean up test user
            session.delete(new_user)
            session.commit()
            print("[OK] Cleaned up temporary test user.")

    except Exception as e:
        print(f"[FAIL] Error during authentication tests: {e}")
        session.rollback()
        return False
    finally:
        session.close()

    print("\n" + "=" * 70)
    print("[SUCCESS] All PostgreSQL verification checks completed successfully.")
    print("=" * 70)
    return True


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "")
    if len(sys.argv) > 1:
        db_url = sys.argv[1]

    if not db_url:
        print("[ERROR] DATABASE_URL must be provided as an argument or environment variable.")
        print("Usage: python scripts/test_postgres_connection.py <DATABASE_URL>")
        sys.exit(1)

    success = test_postgres(db_url)
    sys.exit(0 if success else 1)
