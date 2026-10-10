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
    # Default is SQLite for fast local development and testing
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'database' / 'event_inventory.db'}"
    )

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
