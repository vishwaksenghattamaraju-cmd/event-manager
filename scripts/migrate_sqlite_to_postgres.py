"""
SQLite to PostgreSQL Data Migration Script.
Event Inventory Management System.

Safely copies all existing application data from the SQLite backup/database
into the target PostgreSQL database, preserving IDs, foreign key relationships,
timestamps, and modern password hashes.

Updates PostgreSQL sequence generators to prevent future ID collision errors.
Verifies record counts table-by-table upon completion.
"""

import os
import sys
import argparse
from pathlib import Path

# Ensure root workspace is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, inspect, text, Table, MetaData
from sqlalchemy.orm import sessionmaker
from backend.models.base import Base

# Dependency order for inserting records
TABLE_ORDER = [
    "users",
    "inventory_items",
    "model_runs",
    "events",
    "event_items",
    "inventory_transactions",
    "alerts",
]


def normalize_db_url(url: str) -> str:
    """Normalize postgres:// to postgresql:// and handle driver selection."""
    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            try:
                import pg8000  # noqa: F401
                url = url.replace("postgresql://", "postgresql+pg8000://", 1)
            except ImportError:
                pass
    return url


def run_migration(
    sqlite_path: Path,
    target_url: str,
    clean_target: bool = False,
    verbose: bool = True
) -> dict:
    """
    Executes complete data migration from SQLite to PostgreSQL.
    Returns dictionary with migration status and record counts.
    """
    if not sqlite_path.exists():
        raise FileNotFoundError(f"Source SQLite database not found at: {sqlite_path}")

    target_url = normalize_db_url(target_url)

    if verbose:
        print("=" * 70)
        print("SQLITE TO POSTGRESQL DATA MIGRATION")
        print("=" * 70)
        print(f"Source SQLite:   {sqlite_path.resolve()}")
        import re
        safe_url = re.sub(r":([^:@]+)@", ":****@", target_url)
        print(f"Target Database: {safe_url}")

    # Connect to SQLite
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path.resolve()}")
    sqlite_meta = MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)

    # Connect to Target Database
    pg_engine = create_engine(target_url, pool_pre_ping=True)

    try:
        # 1. Test target connectivity
        try:
            with pg_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            if verbose:
                print("[OK] Successfully connected to target database.")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to target PostgreSQL database: {e}") from e

        # 2. Ensure schema exists on target
        if verbose:
            print("[INFO] Initializing schema on target PostgreSQL...")
        Base.metadata.create_all(bind=pg_engine)

        target_inspector = inspect(pg_engine)
        target_tables = target_inspector.get_table_names()

        # 3. Handle clean target if requested
        if clean_target:
            if verbose:
                print("[INFO] Cleaning target tables (reverse dependency order)...")
            with pg_engine.begin() as conn:
                for table_name in reversed(TABLE_ORDER):
                    if table_name in target_tables:
                        if pg_engine.dialect.name == "postgresql":
                            conn.execute(text(f'TRUNCATE TABLE "{table_name}" CASCADE;'))
                        else:
                            conn.execute(text(f'DELETE FROM "{table_name}";'))
            if verbose:
                print("[OK] Target tables cleared.")

        # 4. Migrate data table-by-table in dependency order
        migration_summary = {}
        target_meta = MetaData()
        target_meta.reflect(bind=pg_engine)

        for table_name in TABLE_ORDER:
            if table_name not in sqlite_meta.tables:
                if verbose:
                    print(f"[SKIP] Table '{table_name}' does not exist in SQLite source.")
                migration_summary[table_name] = {"source": 0, "target": 0, "migrated": 0, "status": "skipped"}
                continue

            src_table = sqlite_meta.tables[table_name]
            tgt_table = target_meta.tables.get(table_name)
            if tgt_table is None:
                raise RuntimeError(f"Target table '{table_name}' was not created in target database.")

            # Read all rows from SQLite
            with sqlite_engine.connect() as src_conn:
                src_rows = src_conn.execute(src_table.select()).mappings().all()

            src_count = len(src_rows)

            # Check existing target rows
            with pg_engine.connect() as tgt_conn:
                existing_target_count = tgt_conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                ).scalar()

            if src_count == 0:
                if verbose:
                    print(f"[INFO] Table '{table_name}': 0 rows in source. Nothing to migrate.")
                migration_summary[table_name] = {
                    "source": 0,
                    "target": existing_target_count,
                    "migrated": 0,
                    "status": "empty",
                }
                continue

            # If records already exist and clean_target wasn't set, handle conflicts
            if existing_target_count > 0 and not clean_target:
                if verbose:
                    print(
                        f"[WARN] Table '{table_name}' already has {existing_target_count} records in target. "
                        f"Migrating missing records by primary key..."
                    )
                with pg_engine.connect() as tgt_conn:
                    existing_ids = set(tgt_conn.execute(text(f'SELECT id FROM "{table_name}"')).scalars().all())
                rows_to_insert = [dict(r) for r in src_rows if r["id"] not in existing_ids]
            else:
                rows_to_insert = [dict(r) for r in src_rows]

            # Insert rows into target
            inserted_count = 0
            if rows_to_insert:
                with pg_engine.begin() as tgt_conn:
                    for r in rows_to_insert:
                        tgt_conn.execute(tgt_table.insert().values(r))
                        inserted_count += 1

            # 5. Reset PostgreSQL identity/serial sequence for this table
            if pg_engine.dialect.name == "postgresql":
                try:
                    with pg_engine.begin() as tgt_conn:
                        seq_res = tgt_conn.execute(
                            text(f"SELECT pg_get_serial_sequence('{table_name}', 'id')")
                        ).scalar()
                        if seq_res:
                            tgt_conn.execute(
                                text(f"SELECT setval('{seq_res}', COALESCE((SELECT MAX(id) FROM \"{table_name}\"), 1), true)")
                            )
                            if verbose:
                                print(f"  [SEQ] Reset sequence for '{table_name}' to MAX(id).")
                except Exception as seq_err:
                    if verbose:
                        print(f"  [NOTE] Sequence reset skipped for '{table_name}': {seq_err}")

            # Verify final count in target
            with pg_engine.connect() as tgt_conn:
                final_target_count = tgt_conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                ).scalar()

            if verbose:
                print(
                    f"[DONE] Table '{table_name}': {src_count} source records -> "
                    f"{inserted_count} inserted -> {final_target_count} total in target."
                )

            migration_summary[table_name] = {
                "source": src_count,
                "migrated": inserted_count,
                "target": final_target_count,
                "status": "success",
            }

        if verbose:
            print("=" * 70)
            print("MIGRATION SUMMARY")
            print("=" * 70)
            total_source = sum(v["source"] for v in migration_summary.values())
            total_migrated = sum(v["migrated"] for v in migration_summary.values())
            total_target = sum(v["target"] for v in migration_summary.values())
            print(f"Total Source Records:   {total_source}")
            print(f"Total Inserted Records: {total_migrated}")
            print(f"Total Target Records:   {total_target}")
            print("=" * 70)

        return migration_summary

    finally:
        sqlite_engine.dispose()
        pg_engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite data to PostgreSQL.")
    parser.add_argument(
        "--source",
        type=str,
        default=str(PROJECT_ROOT / "database" / "event_inventory.db"),
        help="Path to source SQLite database file",
    )
    parser.add_argument(
        "--target-url",
        type=str,
        default=os.getenv("DATABASE_URL", ""),
        help="Target PostgreSQL database URL (defaults to DATABASE_URL environment variable)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Truncate target tables before migrating (clean wipe and reload)",
    )

    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        backup_candidate = PROJECT_ROOT / "database" / "backups" / "event_inventory_backup.db"
        if backup_candidate.exists():
            source_path = backup_candidate

    target_url = args.target_url or os.getenv("DATABASE_URL", "")
    if not target_url:
        print("[ERROR] Target DATABASE_URL must be provided via --target-url or DATABASE_URL env var.", file=sys.stderr)
        print("Example: python scripts/migrate_sqlite_to_postgres.py --target-url postgresql://user:pass@host:5432/dbname", file=sys.stderr)
        sys.exit(1)

    try:
        run_migration(source_path, target_url, clean_target=args.clean)
        print("[SUCCESS] Data migration completed successfully.")
    except Exception as e:
        print(f"[FATAL] Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
