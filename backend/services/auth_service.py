"""Authentication service: handles user registration, login verification, and rate limiting."""

import time
import logging
from typing import Optional, Tuple
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from backend.models.user import User, UserRole

logger = logging.getLogger("event_inventory.auth")

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
    Normalizes input (stripping extra whitespace, case-insensitive match for username/email).
    Returns (user, error_message).
    """
    if not username_or_email or not password:
        return None, "Username/email and password are required."

    raw_ident = (username_or_email or "").strip()
    norm_ident = " ".join(raw_ident.split())
    lower_ident = norm_ident.lower()

    identifier = (client_ip or lower_ident).strip().lower()

    # Rate limit check
    is_allowed, cooldown = check_login_rate_limit(identifier, max_attempts, window_seconds)
    if not is_allowed:
        logger.warning("Rate limit blocked login attempt for identifier '%s'", identifier)
        return None, f"Too many failed login attempts. Please try again in {cooldown} seconds."

    # Look up user by username or email with case-insensitive matching
    try:
        user = (
            db.query(User)
            .filter(
                or_(
                    User.username == norm_ident,
                    func.lower(User.username) == lower_ident,
                    func.lower(User.email) == lower_ident,
                )
            )
            .first()
        )
    except Exception as db_err:
        logger.error("Database query failed during authentication for '%s': %s", norm_ident, db_err, exc_info=True)
        return None, "Database connection error. Please verify database connectivity."

    if not user:
        logger.warning("Authentication failed: user '%s' not found.", norm_ident)
        record_failed_login(identifier)
        return None, "Invalid username or password."

    if not user.check_password(password):
        logger.warning("Authentication failed: incorrect password for user '%s'.", user.username)
        record_failed_login(identifier)
        return None, "Invalid username or password."

    if not user.is_active:
        logger.warning("Authentication rejected: account '%s' is deactivated.", user.username)
        return None, "This account has been deactivated. Please contact an administrator."

    # Reset rate limit tracker on success
    clear_failed_logins(identifier)
    logger.info("Authentication successful for user '%s' (id=%s, role=%s).", user.username, user.id, user.role)
    return user, None


def register_user(
    db: Session, username: str, email: str, password: str, role: str = UserRole.ORGANIZER
) -> Tuple[Optional[User], Optional[str]]:
    """Registers a new user account with specified role (Admin or Organizer)."""
    username = " ".join((username or "").strip().split())
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

    # Check for existing username or email case-insensitively
    try:
        existing_user = (
            db.query(User)
            .filter(
                or_(
                    func.lower(User.username) == username.lower(),
                    func.lower(User.email) == email,
                )
            )
            .first()
        )
        if existing_user:
            if existing_user.username.lower() == username.lower():
                return None, f"Username '{username}' is already taken."
            return None, f"Email '{email}' is already registered."
    except Exception as db_err:
        logger.error("Database query failed during registration check for '%s': %s", username, db_err, exc_info=True)
        return None, "Database connection error. Please verify database connectivity."

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
        logger.info("New user registered successfully: username='%s', email='%s', role='%s' (id=%s)", user.username, user.email, user.role, user.id)
        return user, None
    except Exception as e:
        db.rollback()
        logger.error("User registration database error for '%s': %s", username, e, exc_info=True)
        return None, f"Registration failed due to a database error: {str(e)}"


def register_organizer(
    db: Session, username: str, email: str, password: str
) -> Tuple[Optional[User], Optional[str]]:
    """Registers a new Event Organizer user account."""
    return register_user(db, username, email, password, role=UserRole.ORGANIZER)


def create_admin_user(
    db: Session, username: str, email: str, password: str
) -> Tuple[Optional[User], Optional[str]]:
    """Creates a new Administrator user account (used via CLI)."""
    username = " ".join((username or "").strip().split())
    email = (email or "").strip().lower()

    if not username or len(username) < 3:
        return None, "Username must be at least 3 characters long."
    if not email or "@" not in email:
        return None, "A valid email address is required."
    if not password or len(password) < 6:
        return None, "Password must be at least 6 characters long."

    try:
        existing_user = (
            db.query(User)
            .filter(
                or_(
                    func.lower(User.username) == username.lower(),
                    func.lower(User.email) == email,
                )
            )
            .first()
        )
        if existing_user:
            return None, "A user with that username or email already exists."

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
        logger.info("Admin user created successfully: username='%s', email='%s' (id=%s)", admin.username, admin.email, admin.id)
        return admin, None
    except Exception as e:
        db.rollback()
        logger.error("Failed to create admin user '%s': %s", username, e, exc_info=True)
        return None, f"Failed to create admin user: {str(e)}"


def update_user_profile(
    db: Session,
    user_id: int,
    email: Optional[str] = None,
    current_password: Optional[str] = None,
    new_password: Optional[str] = None,
) -> Tuple[Optional[User], Optional[str]]:
    """Updates user profile information (email and/or password)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None, "User not found."

    if email:
        email = email.strip().lower()
        if not email or "@" not in email:
            return None, "A valid email address is required."
        existing = db.query(User).filter(func.lower(User.email) == email, User.id != user_id).first()
        if existing:
            return None, f"Email '{email}' is already registered to another account."
        user.email = email

    if new_password:
        if not current_password or not user.check_password(current_password):
            return None, "Current password is incorrect. Verification required to change password."
        if len(new_password) < 6:
            return None, "New password must be at least 6 characters long."
        user.set_password(new_password)

    try:
        db.commit()
        db.refresh(user)
        return user, None
    except Exception as e:
        db.rollback()
        return None, f"Failed to update profile: {str(e)}"


def delete_user_account(db: Session, user_id: int) -> Tuple[bool, Optional[str]]:
    """
    Permanently deletes a user account and cleans up associated records.
    Returns (success, error_message).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False, "User not found."

    # Prevent deleting an admin account if it is the only administrator in the system
    if user.is_admin:
        admin_count = db.query(User).filter(User.role == UserRole.ADMIN, User.is_active.is_(True)).count()
        if admin_count <= 1:
            return False, "The primary administrator account cannot be deleted. At least one administrator must remain."

    try:
        from backend.models.event import Event
        from backend.models.inventory import InventoryTransaction

        # Decouple user_id on audit transactions so transaction history remains intact
        db.query(InventoryTransaction).filter(InventoryTransaction.user_id == user.id).update(
            {"user_id": None}, synchronize_session=False
        )

        # Delete any events organized by this user
        events = db.query(Event).filter(Event.organizer_id == user.id).all()
        for ev in events:
            db.delete(ev)

        # Delete the user account
        db.delete(user)
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, f"Failed to delete account: {str(e)}"
