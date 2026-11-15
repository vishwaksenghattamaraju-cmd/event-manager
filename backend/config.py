import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if present
load_dotenv(BASE_DIR / ".env")


class Config:
    """Production & Runtime configuration for Render / PostgreSQL deployment."""

    ENV = os.getenv("FLASK_ENV", "production")
    IS_RENDER = os.getenv("RENDER") == "true" or "RENDER" in os.environ
    IS_PRODUCTION = ENV == "production" or IS_RENDER
    TESTING = False

    SECRET_KEY = os.getenv("SECRET_KEY") or "dev-secret-key-change-in-production-12345"

    # Database URL configuration (PostgreSQL is the exclusive runtime database)
    _raw_db_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("INTERNAL_DATABASE_URL")
        or ""
    ).strip()

    if _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)

    DATABASE_URL = _raw_db_url

    # Connection pooling configuration
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "300"))

    # Session cookie security settings (Render serves apps over HTTPS)
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
