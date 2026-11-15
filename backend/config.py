import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")


class Config:
    """Base configuration loaded from environment variables."""

    # Vercel is serverless: production data must live in a persistent hosted DB.
    IS_VERCEL = os.getenv("VERCEL") == "1" or "VERCEL" in os.environ

    SECRET_KEY = os.getenv("SECRET_KEY")
    if IS_VERCEL and (not SECRET_KEY or SECRET_KEY == "dev-secret-key-change-in-production-12345"):
        raise RuntimeError("SECRET_KEY must be configured in Vercel Environment Variables.")
    SECRET_KEY = SECRET_KEY or "dev-secret-key-change-in-production-12345"

    _db_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRES_PRISMA_URL")
        or os.getenv("POSTGRES_URL_NON_POOLING")
        or os.getenv("SUPABASE_DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("NEON_DATABASE_URL")
        or os.getenv("VERCEL_POSTGRES_URL")
        or ""
    ).strip()

    if IS_VERCEL:
        if not _db_url:
            raise RuntimeError(
                "DATABASE_URL is missing. Configure a persistent PostgreSQL database "
                "(for example Neon or Supabase) in Vercel Environment Variables."
            )
        if _db_url.startswith("postgres://"):
            _db_url = _db_url.replace("postgres://", "postgresql://", 1)
        if not _db_url.startswith(("postgresql://", "postgresql+psycopg2://", "postgresql+pg8000://")):
            raise RuntimeError(
                "SQLite is not supported on Vercel because its filesystem is ephemeral. "
                "Configure a persistent PostgreSQL DATABASE_URL."
            )
    else:
        _db_url = _db_url or f"sqlite:///{BASE_DIR / 'database' / 'event_inventory.db'}"
        if _db_url.startswith("postgres://"):
            _db_url = _db_url.replace("postgres://", "postgresql://", 1)

    DATABASE_URL = _db_url

    # Session cookies: Vercel serves the app over HTTPS.
    SESSION_COOKIE_HTTPONLY = os.getenv("SESSION_COOKIE_HTTPONLY", "True").lower() == "true"
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv(
        "SESSION_COOKIE_SECURE", "True" if IS_VERCEL else "False"
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
