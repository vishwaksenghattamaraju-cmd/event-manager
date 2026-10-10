# Project Blueprint & Implementation Plan: AI-Based Event Inventory Management System

## 1. Requirement to Module Mapping

| Requirement | Target File(s) / Modules | Responsibilities |
| :--- | :--- | :--- |
| **App Initialization & Config** | `backend/app.py`, `backend/config.py` | Flask application factory pattern (`create_app`), config loading from `.env`, CORS, central error handlers, and CLI commands. |
| **Database Connection & Base** | `backend/models/base.py`, `database/migrations/` | SQLAlchemy engine, session management, declarative Base, Alembic environment and migration scripts. |
| **Authentication & RBAC** | `backend/models/user.py`, `backend/routes/auth_routes.py`, `backend/services/auth_service.py` | Password hashing (Werkzeug/bcrypt), login session management (`HttpOnly`, `SameSite`), RBAC decorators (`@admin_required`, `@organizer_or_admin_required`), login rate limiting, and `flask create-admin` CLI command. |
| **Inventory Management** | `backend/models/inventory.py`, `backend/routes/inventory_routes.py`, `backend/services/inventory_service.py` | Item model (returnable vs. consumable, active/deactivated status, physical stock, unavailable stock, thresholds), CRUD endpoints with validation, transaction history recording in `inventory_transactions`. Soft delete enforcement. |
| **Event Management** | `backend/models/event.py`, `backend/routes/event_routes.py`, `backend/services/event_service.py` | Event lifecycle (Draft, Confirmed, Cancelled, Completed), organizer ownership validation (organizer can only access own events, admin accesses all), requirements association. |
| **Booking & Double-Booking Prevention** | `backend/services/booking_service.py`, `backend/routes/booking_routes.py` | **Core Engine**: Overlap detection query (`existing_start < req_end AND existing_end > req_start`), pessimistic locking (`SELECT ... FOR UPDATE` ordered by `item_id ASC`), atomic availability checks, idempotent confirmation, cancel/reschedule/edit stock re-evaluation, consumable deduction on event completion. |
| **Rules-Based Estimator (Fallback)** | `backend/services/estimator_service.py`, `backend/routes/estimator_routes.py` | Fallback calculation based on event type and guest counts (e.g., chairs per guest, tables per group) clearly labelled `"Estimate (rules-based)"`. Active when completed events < 30. |
| **Machine Learning (Stretch)** | `backend/ml/data_generator.py`, `backend/ml/trainer.py`, `backend/ml/predictor.py`, `backend/models/ml_run.py` | Synthetic dataset generator (`is_synthetic=True`), single `RandomForestRegressor` with item encoding and leakage-free features, baseline comparisons (linear regression, ratio rule), time-series / chronological split, MAE/RMSE/R² reporting, tree spread prediction intervals (low/expected/high), drift detection, model serialization with `joblib`. |
| **Alerts & Notifications** | `backend/models/alert.py`, `backend/services/alert_service.py`, `backend/routes/alert_routes.py` | Automatic alert creation on shortage risk or low stock thresholds. "Mark as reviewed" functionality. Always calculated against live stock. |
| **Reporting & Export** | `backend/services/report_service.py`, `backend/routes/report_routes.py` | Usage summary, booking stats, CSV export of inventory and bookings. |
| **Frontend UI (MVP + Extended)** | `frontend/pages/*.html`, `frontend/css/styles.css`, `frontend/js/*.js` | HTML5/CSS3/Vanilla JS interface: `login.html`, `dashboard.html`, `inventory.html`, `events.html`, `prediction.html`, `reports.html`. Communicates solely via REST API. Live database stats, Chart.js charts, responsive glassmorphic/modern UI with error/empty/loading states. |
| **Automated Testing Suite** | `backend/tests/test_auth.py`, `backend/tests/test_inventory.py`, `backend/tests/test_booking.py`, `backend/tests/test_concurrency.py`, `backend/tests/test_estimator.py` | Comprehensive `pytest` test suite covering all 17 mandatory tests (including multi-threaded concurrency locking test). |

---

## 2. Dependencies and Risk Analysis

### Core Dependencies
1. **Python 3.11+ (Currently detected: Python 3.14.6)**: Flask, SQLAlchemy, PyMySQL, python-dotenv, Werkzeug, pytest.
2. **Database Engine**:
   - **Local Dev / Fast Testing**: SQLite 3 (built-in to Python). Great for instant test execution and rapid feature builds.
   - **Production / Concurrency Testing**: MySQL 8 (InnoDB) via PyMySQL. Required for `SELECT ... FOR UPDATE` row-level locking concurrency verification.
3. **Frontend**: Pure HTML5, CSS3, Vanilla JS, and Chart.js via CDN (no Node.js build overhead, completely transparent and beginner-friendly).

### Key Technical Risks & Mitigations
- **Risk 1: SQLite lacks row-level locking (`SELECT ... FOR UPDATE`).**
  - *Mitigation*: The codebase uses standard SQLAlchemy syntax with `.with_for_update()`. During development and basic unit tests, SQLite works seamlessly. For Test #9 (multi-threaded simultaneous booking race condition), tests will run against MySQL InnoDB where row locking is physically enforced.
- **Risk 2: Deadlocks during multi-item booking under concurrent load.**
  - *Mitigation*: Always sort item IDs in ascending order (`ORDER BY item_id ASC`) before locking rows with `FOR UPDATE`. This guarantees a deterministic acquisition order and completely prevents circular wait deadlocks.
- **Risk 3: Timezone inconsistencies across events.**
  - *Mitigation*: All datetimes are stored in UTC (`DateTime(timezone=True)` or ISO8601 UTC strings). Half-open interval arithmetic `[start, end)` is calculated in pure UTC.
- **Risk 4: Accidental double-submits / browser button spam.**
  - *Mitigation*: Idempotency validation on the confirmation endpoint (checking event status transitions atomically so a re-submit returns the existing confirmed state without re-allocating).
- **Risk 5: Premature or misleading ML claims.**
  - *Mitigation*: Hard threshold gate (< 30 completed real events defaults strictly to rules-based estimator labelled "Estimate (rules-based)"). Synthetic data is flagged with `is_synthetic = True` and never mixed into real accuracy statistics.

---

## 3. Step-by-Step Environment Setup Guide (For Windows)

### Step 1: Python Verification
Python is already installed on your machine!
1. Open PowerShell and verify:
   ```powershell
   python --version
   ```
   (Should display `Python 3.14.x`)
2. Virtual environment setup (recommended to keep your project clean):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

### Step 2: Database Setup Options

#### Option A: SQLite (Zero installation, instant start for dev)
- Requires no installation.
- Python handles it automatically.
- Keep `DATABASE_URL=sqlite:///database/event_inventory.db` in your `.env` file.

#### Option B: MySQL 8 for Windows (Recommended for Phase 3 Concurrency Testing)
To run Test #9 (row locking concurrency):
1. **Download MySQL Installer**:
   - Go to [dev.mysql.com/downloads/installer/](https://dev.mysql.com/downloads/installer/)
   - Download the MySQL Community Server 8.x installer (web or full).
2. **Install**:
   - Run the installer, select **Server only** (or Developer Default).
   - Set the root password (e.g. `rootpassword`).
   - Leave the port at `3306`.
3. **Create Database & User**:
   Open MySQL Command Line Client or PowerShell:
   ```sql
   CREATE DATABASE event_inventory_db;
   CREATE USER 'event_user'@'localhost' IDENTIFIED BY 'password123';
   GRANT ALL PRIVILEGES ON event_inventory_db.* TO 'event_user'@'localhost';
   FLUSH PRIVILEGES;
   ```
4. **Update `.env`**:
   ```ini
   DATABASE_URL=mysql+pymysql://event_user:password123@localhost:3306/event_inventory_db
   ```
*(Alternative: If you have or install Docker Desktop, run: `docker run --name mysql-event -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=event_inventory_db -p 3306:3306 -d mysql:8`)*

---

## 4. Work Breakdown by Phases (Overview)

- **Phase 1: Plan** (Current) – Architecture blueprint, directory layout, dependency checks, setup guide, approval.
- **Phase 2: Database + Auth + Inventory** – Core models, Alembic migrations, password hashing, session RBAC, CLI `create-admin`, Inventory CRUD with transaction logging and soft deletes, automated unit tests.
- **Phase 3: Booking Engine** – Availability logic, half-open interval overlap math, `SELECT ... FOR UPDATE` pessimistic locking, event state machine, double-booking prevention, concurrency tests.
- **Phase 4: Frontend (MVP)** – Clean, modern, accessible UI (Login, Dashboard, Inventory, Events) connecting to backend REST API with loading/empty/error states.
- **Phase 5: Rules-Based Estimator + MVP Verification** – Fallback estimator, live Chart.js chart, end-to-end verification, test report.
- **Phase 6: ML Pipeline (Stretch)** – Synthetic data generator, scikit-learn model, baseline comparisons, prediction intervals, prediction UI.
- **Phase 7: Alerts, Reports, Extras (Stretch)** – Shortage alerts, CSV export, event templates, Docker compose.
