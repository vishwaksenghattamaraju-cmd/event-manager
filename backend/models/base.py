"""Database base configuration and session management using SQLAlchemy 2.0."""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

# Base class for all SQLAlchemy declarative models
Base = declarative_base()

# Global engine and session factory
engine = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False)
db_session = scoped_session(SessionLocal)


def get_engine(database_url: str):
    """
    Creates and configures the SQLAlchemy engine.
    - Normalizes postgres:// scheme to postgresql:// for compatibility with Render/PostgreSQL.
    - Handles psycopg2 vs pg8000 drivers gracefully.
    - Configures robust connection pooling for production multi-worker environments (Render/Gunicorn).
    - Preserves StaticPool and SQLite PRAGMAs for automated in-memory testing.
    """
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    # Driver selection / fallback for PostgreSQL
    if database_url.startswith("postgresql://"):
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            try:
                import pg8000  # noqa: F401
                database_url = database_url.replace("postgresql://", "postgresql+pg8000://", 1)
            except ImportError:
                pass

    connect_args = {}
    engine_kwargs = {"pool_pre_ping": True}

    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if database_url == "sqlite:///:memory:":
            engine_kwargs["poolclass"] = StaticPool
    else:
        # Production PostgreSQL connection pool settings for Render
        pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
        pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
        pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "300"))

        engine_kwargs["pool_size"] = pool_size
        engine_kwargs["max_overflow"] = max_overflow
        engine_kwargs["pool_timeout"] = pool_timeout
        engine_kwargs["pool_recycle"] = pool_recycle

        if "pg8000" in database_url:
            import ssl
            if "localhost" not in database_url and "127.0.0.1" not in database_url:
                connect_args["ssl_context"] = ssl.create_default_context()

    eng = create_engine(
        database_url,
        connect_args=connect_args,
        **engine_kwargs,
    )

    # Enable SQLite foreign key constraint enforcement in test mode
    if database_url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return eng


def init_database(database_url: str):
    """
    Initializes the global engine and configures SessionLocal with the engine bind.
    """
    global engine
    engine = get_engine(database_url)
    SessionLocal.configure(bind=engine)
    return engine


def remove_session():
    """Safely closes the scoped session for the current thread/request."""
    if db_session is not None:
        db_session.remove()


def create_all_tables():
    """Helper to create all tables defined on Base (used in migrations, setup, and tests)."""
    if engine is None:
        raise RuntimeError("Database engine is not initialized. Call init_database first.")
    Base.metadata.create_all(bind=engine)

    # Safe schema sync for existing databases
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        if "alerts" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("alerts")]
            if "severity" not in columns:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE alerts ADD COLUMN severity VARCHAR(20) DEFAULT 'WARNING' NOT NULL"))

        if "events" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("events")]
            if "image_url" not in columns:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE events ADD COLUMN image_url TEXT"))
    except Exception:
        pass


def drop_all_tables():
    """Helper to drop all tables defined on Base (used in teardown of testing)."""
    if engine is None:
        raise RuntimeError("Database engine is not initialized. Call init_database first.")
    Base.metadata.drop_all(bind=engine)
