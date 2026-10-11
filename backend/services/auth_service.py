"""Authentication service: handles user registration, login verification, and rate limiting."""

import time
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from backend.models.user import User, UserRole

# In-memory login attempt tracking: { identifier_or_ip: [timestamp1, timestamp2, ...] }
_failed_login_attempts = {}


def check_login_rate_limit(
    identifier: str, max_attempts: int = 5, window_seconds: int = 300
) -> Tuple[bool, int]:
    """
    Checks if a client or account is currently rate-limited due to repeated failures.
    Returns (is_allowed, remaining_cooldown_seconds).
    """
    now = time.time()
    attempts = _failed_login_attempts.get(identifier, [])
    # Filter attempts that occurred within the sliding window
    recent_attempts = [t for t in attempts if now - t < window_seconds]
    _failed_login_attempts[identifier] = recent_attempts

    if len(recent_attempts) >= max_attempts:
        oldest_in_window = recent_attempts[0]
        cooldown = int(window_seconds - (now - oldest_in_window))
        return False, max(1, cooldown)

    return True, 0


def record_failed_login(identifier: str):
    """Records a failed login attempt for rate limiting."""
    now = time.time()
    if identifier not in _failed_login_attempts:
        _failed_login_attempts[identifier] = []
    _failed_login_attempts[identifier].append(now)


def clear_failed_logins(identifier: str):
    """Clears failed login attempts after a successful authentication."""
    if identifier in _failed_login_attempts:
        del _failed_login_attempts[identifier]


def clear_all_failed_logins():
    """Resets all login rate-limit tracking (used in tests and maintenance)."""
    _failed_login_attempts.clear()


def authenticate_user(
    db: Session,
    username_or_email: str,
    password: str,
    client_ip: Optional[str] = None,
    max_attempts: int = 5,
    window_seconds: int = 300,
) -> Tuple[Optional[User], Optional[str]]:
    """
    Validates user credentials against database with rate limiting.
    Returns (user, error_message).
    """
    if not username_or_email or not password:
        return None, "Username/email and password are required."

    identifier = (client_ip or username_or_email).strip().lower()

    # Rate limit check
    is_allowed, cooldown = check_login_rate_limit(identifier, max_attempts, window_seconds)
    if not is_allowed:
        return None, f"Too many failed login attempts. Please try again in {cooldown} seconds."

    # Look up user by username or email
    user = (
        db.query(User)
        .filter(
            (User.username == username_or_email.strip()) | (User.email == username_or_email.strip().lower())
        )
        .first()
    )

    if not user or not user.check_password(password):
        record_failed_login(identifier)
        return None, "Invalid username or password."

    if not user.is_active:
        return None, "This account has been deactivated. Please contact an administrator."

    # Reset rate limit tracker on success
    clear_failed_logins(identifier)
    return user, None


def register_user(
    db: Session, username: str, email: str, password: str, role: str = UserRole.ORGANIZER
) -> Tuple[Optional[User], Optional[str]]:
    """Registers a new user account with specified role (Admin or Organizer)."""
    username = (username or "").strip()
    email = (email or "").strip().lower()
    role = (role or UserRole.ORGANIZER).strip().lower()
    if role not in UserRole.ALL_ROLES:
        role = UserRole.ORGANIZER

    if not username or len(username) < 3:
        return None, "Username must be at least 3 characters long."
    if not email or "@" not in email:
        return None, "A valid email address is required."
    if not password or len(password) < 6:
        return None, "Password must be at least 6 characters long."

    # Check for existing username or email
    existing_user = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if existing_user:
        if existing_user.username == username:
            return None, f"Username '{username}' is already taken."
        return None, f"Email '{email}' is already registered."

    try:
        user = User(
            username=username,
            email=email,
            role=role,
            is_active=True,
        )
        user.set_password(password)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user, None
    except Exception as e:
        db.rollback()
        return None, f"Registration failed: {str(e)}"


def register_organizer(
    db: Session, username: str, email: str, password: str
) -> Tuple[Optional[User], Optional[str]]:
    """Registers a new Event Organizer user account."""
    return register_user(db, username, email, password, role=UserRole.ORGANIZER)


def create_admin_user(
    db: Session, username: str, email: str, password: str
) -> Tuple[Optional[User], Optional[str]]:
    """Creates a new Administrator user account (used via CLI)."""
    username = (username or "").strip()
    email = (email or "").strip().lower()

    if not username or len(username) < 3:
        return None, "Username must be at least 3 characters long."
    if not email or "@" not in email:
        return None, "A valid email address is required."
    if not password or len(password) < 6:
        return None, "Password must be at least 6 characters long."

    existing_user = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if existing_user:
        return None, "A user with that username or email already exists."

    try:
        admin = User(
            username=username,
            email=email,
            role=UserRole.ADMIN,
            is_active=True,
        )
        admin.set_password(password)
        db.add(admin)
        db.commit()
        db.refresh(admin)
        return admin, None
    except Exception as e:
        db.rollback()
        return None, f"Failed to create admin user: {str(e)}"
