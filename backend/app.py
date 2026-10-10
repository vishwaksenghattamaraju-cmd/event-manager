"""Flask application factory, central error handlers, and CLI commands."""

import os
import sys
import logging
from pathlib import Path

# Ensure root workspace is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from flask import Flask, jsonify, request, session
from flask_cors import CORS
import click

from backend.config import Config
from backend.models.base import init_database, create_all_tables, db_session, remove_session
from backend.services.auth_service import create_admin_user
from backend.routes.auth_routes import auth_bp
from backend.routes.inventory_routes import inventory_bp
from backend.routes.event_routes import event_bp
from backend.routes.report_routes import report_bp
from backend.routes.ml_routes import ml_bp
from backend.routes.alert_routes import alert_bp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("event_inventory")


def create_app(config_class=Config) -> Flask:
    """Application factory for the Flask backend."""
    frontend_folder = Path(__file__).resolve().parent.parent / "frontend"
    app = Flask(__name__, static_folder=str(frontend_folder), static_url_path="")
    app.config.from_object(config_class)

    # Initialize CORS
    CORS(app, supports_credentials=True)

    # Initialize Database
    init_database(app.config["DATABASE_URL"])
    # Ensure tables exist (will not overwrite existing data)
    create_all_tables()

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(event_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(ml_bp)
    app.register_blueprint(alert_bp)

    # Static page routing
    @app.route("/")
    def index():
        return app.send_static_file("pages/dashboard.html")

    @app.route("/login")
    def login_page():
        return app.send_static_file("pages/login.html")

    @app.route("/dashboard")
    def dashboard_page():
        return app.send_static_file("pages/dashboard.html")

    @app.route("/inventory")
    def inventory_page():
        return app.send_static_file("pages/inventory.html")

    @app.route("/events")
    def events_page():
        return app.send_static_file("pages/events.html")

    # Teardown database session after each request
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        remove_session()

    # CSRF protection check for mutating requests
    @app.before_request
    def check_csrf_token():
        # Skip CSRF check in automated test mode or safe methods
        if app.config.get("TESTING", False):
            return None

        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            # Exclude login and registration endpoints
            if request.path in ("/api/auth/login", "/api/auth/register"):
                return None

            # If user is logged in, verify CSRF token
            if "user_id" in session:
                expected_token = session.get("csrf_token")
                client_token = request.headers.get("X-CSRF-Token")
                if not client_token or client_token != expected_token:
                    return jsonify({"error": "CSRF validation failed. Missing or invalid token."}), 403

        return None

    # Centralized JSON error handlers
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({"error": "Bad request. Please verify input data."}), 400

    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({"error": "Unauthorized. Please log in."}), 401

    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({"error": "Forbidden. You do not have permission."}), 403

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Resource not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({"error": "Method not allowed on this endpoint."}), 405

    @app.errorhandler(409)
    def conflict(error):
        return jsonify({"error": "Resource conflict."}), 409

    @app.errorhandler(429)
    def ratelimit_exceeded(error):
        return jsonify({"error": "Too many requests. Please slow down."}), 429

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}", exc_info=True)
        # Never expose stack traces to clients!
        return jsonify({"error": "An unexpected internal server error occurred."}), 500

    # CLI command: flask create-admin
    @app.cli.command("create-admin")
    @click.option("--username", prompt="Admin username", help="Administrator username")
    @click.option("--email", prompt="Admin email", help="Administrator email address")
    @click.password_option(prompt="Admin password", help="Administrator password")
    def create_admin_cmd(username, email, password):
        """CLI command to safely create the initial Administrator account."""
        admin, err = create_admin_user(db_session, username, email, password)
        if err:
            click.echo(f"Error: {err}", err=True)
        else:
            click.echo(f"Successfully created admin user '{admin.username}' ({admin.email}).")

    @app.route("/api/health", methods=["GET"])
    def health_check():
        """Health check endpoint."""
        return jsonify({"status": "healthy", "database": "connected"}), 200

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
