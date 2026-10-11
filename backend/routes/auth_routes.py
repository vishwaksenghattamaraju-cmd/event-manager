"""Authentication routes and role-based access control (RBAC) decorators."""

import secrets
from functools import wraps
from flask import Blueprint, request, jsonify, session, g
from backend.models.base import db_session
from backend.models.user import User, UserRole
from backend.services.auth_service import authenticate_user, register_organizer, register_user

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def get_current_user() -> User | None:
    """Helper to retrieve the authenticated user from the current session."""
    user_id = session.get("user_id")
    username = session.get("username")
    if not user_id and not username:
        return None

    if hasattr(g, "current_user") and g.current_user:
        if (user_id and g.current_user.id == user_id) or (username and g.current_user.username == username):
            return g.current_user

    user = None
    if user_id:
        user = db_session.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()

    # Fallback to username lookup if user_id was from another container or reset
    if not user and username:
        user = db_session.query(User).filter(User.username == username, User.is_active.is_(True)).first()
        if user:
            session["user_id"] = user.id
            session.modified = True

    # Fallback for known seeded users if user_id points to standard slot
    if not user and not username and user_id:
        id_to_user = {1: "admin", 2: "organizer", 3: "vishwaksen", 4: "vishwaksen ghattamaraju"}
        fallback_name = id_to_user.get(user_id)
        if fallback_name:
            user = db_session.query(User).filter(User.username == fallback_name, User.is_active.is_(True)).first()
            if user:
                session["user_id"] = user.id
                session["username"] = user.username
                session.modified = True

    # Self-healing in serverless environment:
    # If the user was authenticated with a valid signed session cookie, but this container
    # has a clean /tmp database without this user, restore/seed the user!
    if not user and username:
        try:
            role = session.get("role", UserRole.ORGANIZER)
            email = session.get("email", f"{username}@eventinventory.com")
            user = User(
                username=username,
                email=email,
                role=role,
                is_active=True
            )
            user.set_password("Organizer@123")
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            session["user_id"] = user.id
            session.modified = True
        except Exception:
            db_session.rollback()
            user = db_session.query(User).filter(User.username == username).first()
            if user:
                session["user_id"] = user.id

    g.current_user = user
    return user


def generate_csrf_token() -> str:
    """Generates and stores a unique CSRF token in the session."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def login_required(f):
    """Decorator ensuring that the endpoint requires an authenticated session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required. Please log in."}), 401
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator ensuring that the endpoint can only be accessed by an Administrator."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required. Please log in."}), 401
        active_role = session.get("role", user.role)
        if active_role != UserRole.ADMIN:
            return jsonify({"error": "Forbidden: Administrator privileges required."}), 403
        return f(*args, **kwargs)
    return decorated_function


def organizer_or_admin_required(f):
    """Decorator allowing access to either Event Organizers or Administrators."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required. Please log in."}), 401
        active_role = session.get("role", user.role)
        if active_role not in (UserRole.ADMIN, UserRole.ORGANIZER):
            return jsonify({"error": "Forbidden: Unauthorized role."}), 403
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route("/register", methods=["POST"])
def register():
    """Endpoint to register an account (Organizer or Admin)."""
    data = request.get_json() or {}
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    role = (data.get("role") or UserRole.ORGANIZER).lower().strip()
    if role not in UserRole.ALL_ROLES:
        role = UserRole.ORGANIZER

    user, error = register_user(db_session, username, email, password, role=role)
    if error:
        return jsonify({"error": error}), 400

    # Auto-login after registration
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    session["username"] = user.username
    session["email"] = user.email
    session["role"] = user.role
    csrf_token = generate_csrf_token()

    return jsonify({
        "message": f"{role.capitalize()} registration successful.",
        "user": user.to_dict(),
        "csrf_token": csrf_token
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """Endpoint for user login with password verification and rate limiting."""
    data = request.get_json() or {}
    username_or_email = (
        data.get("username_or_email")
        or data.get("username")
        or data.get("email")
    )
    password = data.get("password")
    client_ip = request.remote_addr

    user, error = authenticate_user(
        db_session,
        username_or_email,
        password,
        client_ip=client_ip
    )
    if error:
        status_code = 429 if "Too many" in error else 401
        return jsonify({"error": error}), status_code

    # Establish session
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    session["username"] = user.username
    session["email"] = user.email
    session["role"] = user.role
    csrf_token = generate_csrf_token()

    return jsonify({
        "message": "Login successful.",
        "user": user.to_dict(),
        "csrf_token": csrf_token
    }), 200


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Endpoint to terminate user session."""
    session.clear()
    return jsonify({"message": "Logged out successfully."}), 200


@auth_bp.route("/me", methods=["GET"])
def get_profile():
    """Returns current user details and CSRF token if authenticated."""
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False, "user": None}), 200

    session.permanent = True
    csrf_token = generate_csrf_token()
    user_dict = user.to_dict()
    active_role = session.get("role", user.role)
    user_dict["role"] = active_role
    user_dict["is_admin"] = (active_role == UserRole.ADMIN)
    return jsonify({
        "authenticated": True,
        "user": user_dict,
        "csrf_token": csrf_token
    }), 200


@auth_bp.route("/toggle-role", methods=["POST"])
@login_required
def toggle_role():
    """Toggles current session role between Admin and Organizer for seamless testing/demonstration."""
    user = get_current_user()
    current_role = session.get("role", user.role if user else UserRole.ORGANIZER)
    new_role = UserRole.ADMIN if current_role == UserRole.ORGANIZER else UserRole.ORGANIZER

    session.permanent = True
    session["role"] = new_role

    if user:
        user.role = new_role
        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
        session["user_id"] = user.id
        session["username"] = user.username
        session["email"] = user.email

    session.modified = True
    csrf_token = generate_csrf_token()

    user_dict = user.to_dict() if user else {}
    user_dict["role"] = new_role
    user_dict["is_admin"] = (new_role == UserRole.ADMIN)

    return jsonify({
        "message": f"Switched role to {new_role.capitalize()}.",
        "role": new_role,
        "is_admin": (new_role == UserRole.ADMIN),
        "user": user_dict,
        "csrf_token": csrf_token
    }), 200

