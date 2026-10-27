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

    # Secret key for signing session cookies
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production-12345")

    # Database connection URL
    # Automatically adapts to writable /tmp storage if running in Vercel serverless environment
    _is_vercel = os.getenv("VERCEL") == "1" or "VERCEL" in os.environ
    _default_db = "sqlite:////tmp/event_inventory.db" if _is_vercel else f"sqlite:///{BASE_DIR / 'database' / 'event_inventory.db'}"
    _db_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRES_PRISMA_URL")
        or os.getenv("POSTGRES_URL_NON_POOLING")
        or os.getenv("NEON_DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or _default_db
    ).strip()

    # Normalization: ensure postgresql:// scheme for SQLAlchemy 2.0+
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)

    # Safety checks for Vercel
    if _is_vercel and _db_url.startswith("sqlite:///") and not _db_url.startswith("sqlite:////tmp/"):
        _db_url = "sqlite:////tmp/event_inventory.db"
    elif "user:password@ep-host.neon.tech" in _db_url:
        # Fallback to local /tmp sqlite if placeholder connection string was pasted without real credentials
        _db_url = "sqlite:////tmp/event_inventory.db"

    DATABASE_URL = _db_url

    # Session cookie security settings
    SESSION_COOKIE_HTTPONLY = os.getenv("SESSION_COOKIE_HTTPONLY", "True").lower() == "true"
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"
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
