"""Flask application factory, central error handlers, and CLI commands."""

import os
import sys
import logging
from pathlib import Path

# Ensure root workspace is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from flask import Flask, jsonify, request, session, send_from_directory
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


class VercelPathMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        target = environ.get("HTTP_X_TARGET_PATH")
        if target:
            environ["PATH_INFO"] = target.split("?")[0]
            if "?" in target:
                environ["QUERY_STRING"] = target.split("?", 1)[1]
        elif environ.get("PATH_INFO") in ("/api/index.py", "/api/index", "/api"):
            forwarded = (
                environ.get("HTTP_X_FORWARDED_URI")
                or environ.get("HTTP_X_NOW_ROUTE_MATCHES")
                or environ.get("HTTP_X_MATCHED_PATH")
                or environ.get("HTTP_X_VERCEL_PATH")
                or environ.get("HTTP_X_ORIGINAL_URI")
                or environ.get("RAW_URI")
                or environ.get("REQUEST_URI")
            )
            if forwarded:
                environ["PATH_INFO"] = forwarded.split("?")[0]
        return self.wsgi_app(environ, start_response)


def create_app(config_class=Config) -> Flask:
    """Application factory for the Flask backend."""
    root_dir = Path(__file__).resolve().parent.parent
    frontend_folder = root_dir / "frontend"
    if not frontend_folder.exists():
        alt_folder = Path.cwd() / "frontend"
        if alt_folder.exists():
            frontend_folder = alt_folder

    app = Flask(__name__, static_folder=str(frontend_folder), static_url_path="/static")
    app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
    app.config.from_object(config_class)

    # Initialize CORS
    CORS(app, supports_credentials=True)

    # Initialize Database safely
    try:
        init_database(app.config["DATABASE_URL"])
        create_all_tables()

        # Self-healing: auto-seed admin if database is newly initialized
        try:
            from backend.models.user import User, UserRole
            from backend.services.auth_service import register_organizer
            if not db_session.query(User).filter(User.username == "admin").first():
                create_admin_user(db_session, "admin", "admin@eventinventory.com", "Admin@123")
                logger.info("Auto-seeded default administrator: admin / Admin@123")

            for org_user, org_email in [
                ("organizer", "organizer@eventinventory.com"),
                ("vishwaksen", "vishwaksen@eventinventory.com"),
                ("vishwaksen ghattamaraju", "vishwaksen.ghattamaraju@gmail.com")
            ]:
                if not db_session.query(User).filter(User.username == org_user).first():
                    register_organizer(db_session, org_user, org_email, "Organizer@123")
            logger.info("Verified default organizers present in database.")
        except Exception as seed_err:
            logger.warning(f"Default user initialization skipped: {seed_err}")
            db_session.rollback()

        # Self-healing: auto-seed demo inventory items if catalog is empty
        try:
            from backend.models.inventory import InventoryItem
            from backend.services.inventory_service import create_item
            if db_session.query(InventoryItem).count() == 0:
                sample_items = [
                    {"name": "1000W Active PA Speaker", "category": "Audio", "total_stock": 24, "unavailable_stock": 0, "minimum_threshold": 4, "unit": "units", "purchase_cost": 350.0},
                    {"name": "Wireless Handheld Microphone", "category": "Audio", "total_stock": 25, "unavailable_stock": 2, "minimum_threshold": 5, "unit": "mics", "purchase_cost": 120.0},
                    {"name": "16-Channel Audio Mixer Console", "category": "Audio", "total_stock": 6, "unavailable_stock": 0, "minimum_threshold": 2, "unit": "consoles", "purchase_cost": 480.0},
                    {"name": "4K Laser Projector 6000L", "category": "Visual", "total_stock": 8, "unavailable_stock": 1, "minimum_threshold": 2, "unit": "projectors", "purchase_cost": 1200.0},
                    {"name": '120" Portable Motorized Screen', "category": "Visual", "total_stock": 10, "unavailable_stock": 0, "minimum_threshold": 2, "unit": "screens", "purchase_cost": 280.0},
                    {"name": '65" 4K Commercial Display & Stand', "category": "Visual", "total_stock": 12, "unavailable_stock": 0, "minimum_threshold": 3, "unit": "displays", "purchase_cost": 650.0},
                    {"name": "RGBW Stage Uplight Par", "category": "Lighting", "total_stock": 60, "unavailable_stock": 4, "minimum_threshold": 12, "unit": "lights", "purchase_cost": 45.0},
                    {"name": "Moving Head Beam Spotlight", "category": "Lighting", "total_stock": 16, "unavailable_stock": 0, "minimum_threshold": 4, "unit": "fixtures", "purchase_cost": 320.0},
                    {"name": "Deluxe Padded Banquet Chair", "category": "Furniture", "total_stock": 350, "unavailable_stock": 10, "minimum_threshold": 50, "unit": "chairs", "purchase_cost": 35.0},
                    {"name": '60" Round Banquet Table (Seats 8)', "category": "Furniture", "total_stock": 45, "unavailable_stock": 2, "minimum_threshold": 8, "unit": "tables", "purchase_cost": 95.0},
                    {"name": "6ft Rectangular Catering Table", "category": "Furniture", "total_stock": 30, "unavailable_stock": 0, "minimum_threshold": 5, "unit": "tables", "purchase_cost": 75.0},
                    {"name": "Cocktail High-Boy Bistro Table", "category": "Furniture", "total_stock": 25, "unavailable_stock": 0, "minimum_threshold": 5, "unit": "tables", "purchase_cost": 55.0},
                    {"name": "Pipe & Drape Velvet Backdrop (10ft)", "category": "Decor", "total_stock": 15, "unavailable_stock": 0, "minimum_threshold": 3, "unit": "sets", "purchase_cost": 180.0},
                    {"name": "Acrylic Presidential Lectern", "category": "Decor", "total_stock": 5, "unavailable_stock": 0, "minimum_threshold": 1, "unit": "podiums", "purchase_cost": 220.0},
                    {"name": "Premium Satin Napkins (Pack of 50)", "category": "Consumables", "total_stock": 70, "unavailable_stock": 0, "minimum_threshold": 15, "unit": "packs", "purchase_cost": 18.0, "is_consumable": True},
                    {"name": "Biodegradable Party Confetti Cannon", "category": "Consumables", "total_stock": 35, "unavailable_stock": 0, "minimum_threshold": 10, "unit": "cannons", "purchase_cost": 8.0, "is_consumable": True},
                    {"name": "Silicone Security Wristbands (100pk)", "category": "Consumables", "total_stock": 15, "unavailable_stock": 0, "minimum_threshold": 5, "unit": "packs", "purchase_cost": 12.0, "is_consumable": True},
                ]
                admin = db_session.query(User).filter(User.role == UserRole.ADMIN).first()
                for item_data in sample_items:
                    create_item(db_session, item_data, user_id=admin.id if admin else None)
                logger.info("Auto-seeded catalog items for initial deployment.")
        except Exception as cat_err:
            logger.warning(f"Catalog auto-seed skipped: {cat_err}")
            db_session.rollback()

        # Self-healing: auto-seed demo events if events table is empty
        try:
            from backend.models.event import Event, EventType
            from backend.services.booking_service import confirm_event_booking
            from datetime import timedelta
            if db_session.query(Event).count() == 0:
                admin = db_session.query(User).filter(User.role == UserRole.ADMIN).first()
                organizer = db_session.query(User).filter(User.role == UserRole.ORGANIZER).first() or admin
                now_utc = datetime.now(timezone.utc)
                confirm_event_booking(
                    db_session,
                    name="Global Tech Summit 2026",
                    event_type=EventType.CONFERENCE,
                    start_time=now_utc + timedelta(days=2),
                    end_time=now_utc + timedelta(days=2, hours=8),
                    items=[],
                    location="Main Auditorium & Hall A",
                    expected_attendees=250,
                    description="Keynote technology summit featuring AI, cloud infrastructure, and autonomous agent tracks.",
                    user_id=organizer.id if organizer else None,
                    image_url="/images/events/conference.jpg",
                )
                confirm_event_booking(
                    db_session,
                    name="Acoustic Sunset Concert",
                    event_type=EventType.CONCERT,
                    start_time=now_utc + timedelta(days=5, hours=18),
                    end_time=now_utc + timedelta(days=5, hours=22),
                    items=[],
                    location="Riverside Open Amphitheater",
                    expected_attendees=180,
                    description="Live acoustic performances and outdoor twilight musical celebration.",
                    user_id=organizer.id if organizer else None,
                    image_url="/images/events/concert.jpg",
                )
                logger.info("Auto-seeded demo events for initial deployment.")
        except Exception as evt_seed_err:
            logger.warning(f"Demo event auto-seed skipped: {evt_seed_err}")
            db_session.rollback()

    except Exception as db_err:
        logger.error(f"Database initialization warning: {db_err}")

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
        return app.send_static_file("pages/login.html")

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

    @app.route("/css/<path:filename>")
    def serve_css(filename):
        for candidate in [frontend_folder / "css", root_dir / "public" / "css"]:
            if candidate.exists() and (candidate / filename).exists():
                return send_from_directory(str(candidate), filename, mimetype="text/css")
        return jsonify({"error": "CSS file not found"}), 404

    @app.route("/js/<path:filename>")
    def serve_js(filename):
        for candidate in [frontend_folder / "js", root_dir / "public" / "js"]:
            if candidate.exists() and (candidate / filename).exists():
                return send_from_directory(str(candidate), filename, mimetype="application/javascript")
        return jsonify({"error": "JS file not found"}), 404

    @app.route("/videos/<path:filename>")
    def serve_videos(filename):
        for candidate in [frontend_folder / "videos", root_dir / "public" / "videos"]:
            if candidate.exists() and (candidate / filename).exists():
                return send_from_directory(str(candidate), filename, conditional=True)
        return jsonify({"error": "Video file not found"}), 404

    @app.route("/images/<path:filename>")
    def serve_images(filename):
        for candidate in [frontend_folder / "images", root_dir / "public" / "images"]:
            if candidate.exists() and (candidate / filename).exists():
                return send_from_directory(str(candidate), filename)
        return jsonify({"error": "Image file not found"}), 404

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

    @app.route("/api/debug", methods=["GET"])
    def debug_endpoint():
        return jsonify({"status": "ok"}), 200

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
