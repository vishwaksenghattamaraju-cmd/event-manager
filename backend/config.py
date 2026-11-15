import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if present
load_dotenv(BASE_DIR / ".env")


class Config:
    """Configuration supporting PostgreSQL in production and verified SQLite fallback in local development."""

    FLASK_ENV = os.getenv("FLASK_ENV", "").strip().lower()
    IS_RENDER = os.getenv("RENDER") == "true" or "RENDER" in os.environ
    IS_PRODUCTION = (FLASK_ENV == "production") or IS_RENDER
    ENV = "production" if IS_PRODUCTION else "development"
    TESTING = False

    SECRET_KEY = os.getenv("SECRET_KEY") or "dev-secret-key-change-in-production-12345"

    # Database URL resolution supporting PostgreSQL and local SQLite fallback
    _raw_db_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("INTERNAL_DATABASE_URL")
        or os.getenv("POSTGRES_PRISMA_URL")
        or os.getenv("POSTGRES_URL_NON_POOLING")
        or os.getenv("SUPABASE_DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("NEON_DATABASE_URL")
        or os.getenv("VERCEL_POSTGRES_URL")
        or ""
    ).strip()

    if _raw_db_url:
        # Normalize postgres:// scheme to postgresql:// for SQLAlchemy 2.0
        if _raw_db_url.startswith("postgres://"):
            _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)
    else:
        # Production deployment: PostgreSQL is strictly mandatory. Never fall back to SQLite on Render.
        # Local development: Safely fall back to the existing verified SQLite database if available.
        if not IS_PRODUCTION and not IS_RENDER:
            local_sqlite_path = BASE_DIR / "database" / "event_inventory.db"
            if local_sqlite_path.exists():
                _raw_db_url = f"sqlite:///{local_sqlite_path.resolve()}"

    DATABASE_URL = _raw_db_url

    # Connection pooling configuration
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "300"))

    # Session cookie security settings (Secure on HTTPS/Render; unforced on local HTTP)
    SESSION_COOKIE_HTTPONLY = os.getenv("SESSION_COOKIE_HTTPONLY", "True").lower() == "true"
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv(
        "SESSION_COOKIE_SECURE", "True" if (IS_PRODUCTION or IS_RENDER) else "False"
    ).lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # Rate limiting configuration (max attempts per window)
    LOGIN_RATE_LIMIT_ATTEMPTS = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minutes


class TestConfig(Config):
    """Configuration for automated tests."""
    TESTING = True
    # In-memory SQLite for fast, isolated unit tests
    DATABASE_URL = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key"
    LOGIN_RATE_LIMIT_ATTEMPTS = 50  # relaxed for rapid testing
