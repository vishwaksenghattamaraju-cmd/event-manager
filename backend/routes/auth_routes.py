"""Authentication routes and role-based access control (RBAC) decorators."""

import secrets
from functools import wraps
from flask import Blueprint, request, jsonify, session, g
from backend.models.base import db_session
from backend.models.user import User, UserRole
from backend.services.auth_service import authenticate_user, register_organizer

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def get_current_user() -> User | None:
    """Helper to retrieve the authenticated user from the current session."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    if not hasattr(g, "current_user") or not g.current_user or g.current_user.id != user_id:
        g.current_user = db_session.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    return g.current_user


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
        if user.role not in (UserRole.ADMIN, UserRole.ORGANIZER):
            return jsonify({"error": "Forbidden: Unauthorized role."}), 403
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route("/register", methods=["POST"])
def register():
    """Endpoint for Event Organizers to register an account."""
    data = request.get_json() or {}
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    user, error = register_organizer(db_session, username, email, password)
    if error:
        return jsonify({"error": error}), 400

    # Auto-login after registration
    session.clear()
    session["user_id"] = user.id
    session["role"] = user.role
    csrf_token = generate_csrf_token()

    return jsonify({
        "message": "Registration successful.",
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
    session["user_id"] = user.id
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

    csrf_token = generate_csrf_token()
    user_dict = user.to_dict()
    if "role" in session:
        user_dict["role"] = session["role"]
        user_dict["is_admin"] = (session["role"] == UserRole.ADMIN)
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
    session["role"] = new_role

    user_dict = user.to_dict() if user else {}
    user_dict["role"] = new_role
    user_dict["is_admin"] = (new_role == UserRole.ADMIN)

    return jsonify({
        "message": f"Switched role to {new_role.capitalize()}.",
        "role": new_role,
        "is_admin": (new_role == UserRole.ADMIN),
        "user": user_dict
    }), 200

