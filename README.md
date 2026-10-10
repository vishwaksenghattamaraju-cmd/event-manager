# 🎪 AI-Based Event Inventory Management System for Small-Scale Events

> A production-ready, database-backed web application that prevents equipment double-booking, manages physical inventory with an immutable audit ledger, and leverages machine learning to predict required event supplies and alert on shortage risks.

---

## ⚡ The Golden Rule of the System

> **"Machine learning only recommends — the database strictly enforces physical reality."**
> 
> The ML model suggests items and quantities based on event type, attendee count, and duration. However, the backend database strictly checks availability, prevents double-booking, and never allows reservations to exceed physical warehouse inventory.

---

## 🌟 Core Features

- **🛡️ Concurrency & Double-Booking Prevention**:
  - Half-open interval mathematical overlap queries `[start - setup_buffer, end + teardown_buffer)`.
  - Deterministic ascending-order pessimistic row locking (`SELECT ... FOR UPDATE`) prevents deadlocks and race conditions.
  - Automatic reservation release on cancellation or rescheduling.
- **📦 Physical Inventory Management**:
  - Full CRUD operations with soft-delete safeguard (`is_active=False`).
  - Strict distinction between **Returnable** assets (chairs, speakers, projectors) and **Consumable** supplies (napkins, confetti, wristbands).
  - Immutable append-only transaction audit ledger (`inventory_transactions`) tracks every unit movement.
- **🤖 Dual-Model Machine Learning Layer**:
  - **Model 1 (`RandomForestRegressor`)**: Predicts required quantities for 6 essential equipment classes with 90% confidence intervals.
  - **Model 2 (`RandomForestClassifier`)**: Analyzes schedule congestion 14 days in advance and classifies shortage risk (`High`, `Medium`, `Low`).
  - Automatic fallback heuristics ensure 100% uptime even if ML models are missing.
- **🔔 Real-Time Alert & Watchdog Engine**:
  - Automatic `LOW_STOCK` warnings and `OUT_OF_STOCK` critical alerts when safety thresholds are breached.
  - Auto-resolves alerts when stock is replenished above threshold.
  - High shortage risk radar alerts organizers before weekend congestion occurs.
  - Interactive top navigation bell with live badge and resolution drawer.
- **📥 One-Click CSV Export**:
  - Export full live inventory catalog with health status and unit costs.
  - Export historical and upcoming event booking schedules.
- **🎨 Modern Dark Glassmorphism Frontend**:
  - Custom Vanilla CSS with Outfit & JetBrains Mono typography.
  - Real-time stock distribution Chart.js graphs.
  - Debounced live availability checker in booking modal.

---

## 🏗️ System Architecture

```text
[ Web Browser ]
      │
      ▼ (HTML5, Vanilla CSS Glassmorphism, Chart.js, Fetch API)
[ Flask REST API ]
  ├── Auth & CSRF Middleware (Session Cookies + Role-Based Access Control)
  ├── Inventory Service (Stock tracking & Immutable audit transactions)
  ├── Booking Service (Deterministic row locking & Overlap buffer math)
  ├── Alert Engine (Threshold watchdog & Auto-resolution)
  └── ML Service (Random Forest regressors/classifiers + Fallbacks)
      │
      ├── [ SQLAlchemy 2.0 ORM ] ──► [ SQLite 3 / MySQL 8.0 ]
      └── [ Scikit-Learn Models ] ──► [ ml/models/*.joblib ]
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.11+** (Python 3.14 recommended)
- **Git**

### 2. Installation & Setup

```powershell
# 1. Clone the repository
git clone <repo-url>
cd "mini project"

# 2. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # On Windows
# source .venv/bin/activate    # On Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt
```

### 3. Initialize Database & Seed Demo Data

Run the one-command demo seeder to populate realistic inventory, sample events, and test accounts:

```powershell
python scripts/seed_demo_data.py
```

### 4. Start the Application

```powershell
# Development server:
python backend/app.py

# OR Production WSGI server (Waitress):
python wsgi.py
```

Open your browser to: **`http://127.0.0.1:5000`**

---

## 🔑 Default Credentials

| Role | Username | Password | Email |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `AdminSecure123!` | `admin@eventinventory.local` |
| **Event Organizer** | `organizer` | `OrganizerPass123!` | `organizer@eventinventory.local` |

*Note: You can also register a new Event Organizer directly from the login page (`/login`).*

---

## 🐳 Docker Deployment

The system is fully containerized with MySQL 8.0 and automatic database initialization:

```powershell
# Start both MySQL 8.0 database and Flask web app
docker compose up --build

# Access the app at http://localhost:5000
```

---

## 🧪 Automated Testing (Pytest)

The project includes an exhaustive suite of **32 automated tests** covering security, transactions, concurrency, machine learning, and alerts:

```powershell
# Run all tests
.venv\Scripts\pytest backend\tests -v

# Run specific phase tests:
.venv\Scripts\pytest backend\tests\test_auth.py -v              # Auth & CSRF
.venv\Scripts\pytest backend\tests\test_inventory.py -v         # Inventory CRUD & Audit
.venv\Scripts\pytest backend\tests\test_booking_engine.py -v    # Locking & Overlaps
.venv\Scripts\pytest backend\tests\test_ml.py -v                # ML Models & Predictions
.venv\Scripts\pytest backend\tests\test_alerts_and_export.py -v # Alerts & CSV Exports
```

### Test Coverage Summary:
- **Test #1–#3**: User registration, bcrypt authentication, and CSRF protection.
- **Test #4, #6–#8**: Inventory CRUD, immutable transaction logs, and soft deletes.
- **Test #9–#14**: Concurrency locking, double-booking rejection, buffer times, and consumable deduction.
- **Test #15–#16**: Role separation (Admin vs. Organizer) and live SQL dashboard metrics.
- **Test #17–#21**: ML predictions, confidence intervals, edge-case fallbacks, and shortage risk scoring.
- **Test #22–#24**: Stock alerts, auto-resolution, CSV formatting, and ML risk alerts.

---

## 📡 REST API Reference

### Authentication (`/api/auth`)
| Method | Endpoint | Access | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/register` | Public | Register new Event Organizer account |
| `POST` | `/api/auth/login` | Public | Authenticate user & issue session cookie |
| `POST` | `/api/auth/logout` | Authenticated | Destroy active session |
| `GET` | `/api/auth/me` | Authenticated | Fetch current user profile & CSRF token |

### Inventory Catalog (`/api/inventory`)
| Method | Endpoint | Access | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/inventory` | Authenticated | List catalog with search & category filters |
| `POST` | `/api/inventory` | Admin | Create a new inventory item |
| `GET` | `/api/inventory/<id>` | Authenticated | Get item details & physical stock |
| `PUT` | `/api/inventory/<id>` | Admin | Update item metadata or stock |
| `DELETE` | `/api/inventory/<id>` | Admin | Soft-delete inventory item |
| `POST` | `/api/inventory/<id>/adjust` | Admin | Adjust physical stock with audit reason |
| `POST` | `/api/inventory/<id>/unavailable` | Admin | Mark stock as damaged/in-maintenance |
| `GET` | `/api/inventory/<id>/transactions` | Admin | Retrieve immutable audit transaction log |

### Event Bookings (`/api/events`)
| Method | Endpoint | Access | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/events` | Authenticated | List events (Admins see all, Organizers see own) |
| `POST` | `/api/events` | Authenticated | Create a draft event booking |
| `POST` | `/api/events/check-availability` | Authenticated | Real-time availability calculation |
| `POST` | `/api/events/<id>/confirm` | Authenticated | Atomically confirm booking with row locks |
| `POST` | `/api/events/<id>/cancel` | Authenticated | Cancel booking & release reservations |
| `PUT` | `/api/events/<id>` | Authenticated | Reschedule event or update items |
| `POST` | `/api/events/<id>/complete` | Authenticated | Mark complete & deduct consumables |

### Machine Learning (`/api/ml`)
| Method | Endpoint | Access | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/ml/predict-items` | Authenticated | Predict required items & confidence intervals |
| `GET` | `/api/ml/shortage-risks` | Authenticated | Get 14-day ML shortage risk radar |
| `POST` | `/api/ml/retrain` | Admin | Retrain ML models & log run metrics |

### Alerts & Reports (`/api/alerts`, `/api/reports`)
| Method | Endpoint | Access | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/alerts` | Authenticated | List unresolved stock and risk alerts |
| `POST` | `/api/alerts/<id>/resolve` | Authenticated | Mark an alert as resolved |
| `POST` | `/api/alerts/scan` | Admin | Trigger system-wide inventory alert scan |
| `GET` | `/api/reports/dashboard-summary` | Authenticated | Live dashboard metrics & category stats |
| `GET` | `/api/reports/inventory-csv` | Authenticated | Download complete inventory catalog CSV |
| `GET` | `/api/reports/event-summary-csv` | Authenticated | Download event bookings summary CSV |

---

## 📁 Project Directory Layout

```text
mini project/
├── backend/
│   ├── models/           # SQLAlchemy models (User, Inventory, Event, Alert, MLRun)
│   ├── routes/           # Flask Blueprints (auth, inventory, event, report, ml, alert)
│   ├── services/         # Business logic (auth, inventory, booking, ml, alert)
│   ├── tests/            # Pytest test suite (32 automated tests)
│   ├── app.py            # Application factory & CSRF middleware
│   └── config.py         # Config classes (Dev, Test, Prod)
├── frontend/
│   ├── css/styles.css    # Dark glassmorphism design system
│   ├── js/               # Modular vanilla JS (api.js, dashboard.js, inventory.js, events.js, login.js)
│   └── pages/            # Semantic HTML pages (login, dashboard, inventory, events)
├── ml/
│   ├── models/           # Serialized model artifacts (.joblib)
│   ├── generate_training_data.py # Synthetic event dataset generator
│   └── train_models.py   # Training script for Model 1 & Model 2
├── scripts/
│   └── seed_demo_data.py # Demo database population script
├── docs/                 # Architecture specifications & Phase plans
├── Dockerfile            # Production container specification
├── docker-compose.yml    # Multi-container orchestration (MySQL 8 + Web)
├── wsgi.py               # WSGI entrypoint for Waitress / Gunicorn
└── requirements.txt      # Python dependencies
```

---

## 👨‍💻 Author & Academic Submission

Developed for the Engineering Mini Project: **"AI-Based Event Inventory Management System for Small-Scale Events"**. Built with an emphasis on code clarity, database concurrency safety, statistical validation, and production deployment standards.
