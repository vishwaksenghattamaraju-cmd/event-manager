"""Database base configuration and session management using SQLAlchemy 2.0."""

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
    Applies SQLite-specific settings (foreign keys PRAGMA and StaticPool for in-memory tests).
    Normalizes postgres:// scheme to postgresql:// for compatibility with Neon/Supabase/Vercel Postgres.
    Gracefully handles psycopg2 vs pg8000 drivers in serverless environments.
    """
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    # Driver fallback for serverless Python on PostgreSQL
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
        # Serverless PostgreSQL settings (auto-recycle connections, handle cold starts)
        engine_kwargs["pool_recycle"] = 300
        engine_kwargs["pool_size"] = 5
        engine_kwargs["max_overflow"] = 10

    eng = create_engine(
        database_url,
        connect_args=connect_args,
        **engine_kwargs,
    )

    # Enable SQLite foreign key constraint enforcement
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
    """Helper to create all tables defined on Base (used in development and testing)."""
    if engine is None:
        raise RuntimeError("Database engine is not initialized. Call init_database first.")
    Base.metadata.create_all(bind=engine)

    # Safe lightweight schema sync for development database
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
