# Manual Render Deployment & PostgreSQL Migration Guide
**Event Inventory Management System (Flask + PostgreSQL)**

This guide provides step-by-step instructions for manually deploying your Flask application and PostgreSQL database to Render, migrating your existing application records, and verifying production functionality.

---

## Architecture Overview

- **Web Service**: Python 3.11 / Flask application served by Gunicorn (`wsgi:app`).
- **Database**: Render Managed PostgreSQL.
- **Connection**: Internal Database URL (secure, private network within Render) or External Database URL (for running the one-time data migration from your local workstation).
- **Health Check**: `GET /api/health` performs a live `SELECT 1` query to verify database connectivity.

---

## Step 1: Create Render PostgreSQL Database

1. Log into your [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** in the top navigation bar and select **PostgreSQL**.
3. Configure the database instance:
   - **Name**: `event-inventory-db` (or any chosen name)
   - **Database**: `event_inventory`
   - **User**: `event_admin`
   - **Region**: Select the region closest to you (e.g. `Oregon (US West)` or `Frankfurt (EU Central)`). *Note: Ensure you select the exact same region for your Web Service later.*
   - **PostgreSQL Version**: `16` (default recommended)
   - **Plan**: `Free` (or `Starter`)
4. Click **Create Database**.
5. Wait ~60 seconds until the database status changes to **Available**.

---

## Step 2: Locate Database Connection URLs

In your Render PostgreSQL dashboard, scroll down to the **Connections** section:

1. **Internal Database URL**:
   - Format: `postgres://event_admin:PASSWORD@dpg-xxxxxx-a/event_inventory`
   - **Use**: This is used exclusively by your Render Web Service. It connects securely over Render's internal private network with zero public egress fees.
2. **External Database URL**:
   - Format: `postgres://event_admin:PASSWORD@dpg-xxxxxx-a.oregon-postgres.render.com/event_inventory?sslmode=require`
   - **Use**: This is used by your local workstation to run the initial data migration script (`scripts/migrate_sqlite_to_postgres.py`) and verify connectivity.

---

## Step 3: Run the Data Migration from Local SQLite to Render PostgreSQL

Before starting the web service, populate your Render PostgreSQL database with all 31 existing records from your SQLite database.

1. On your local machine, open your terminal in the project directory.
2. Run the migration script using your Render **External Database URL**:
   ```bash
   # Windows PowerShell
   .\venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py --target-url "PASTE_YOUR_EXTERNAL_DATABASE_URL_HERE" --clean

   # Linux / macOS
   ./venv/bin/python scripts/migrate_sqlite_to_postgres.py --target-url "PASTE_YOUR_EXTERNAL_DATABASE_URL_HERE" --clean
   ```
3. The script will:
   - Create all tables with constraints and indexes (`users`, `inventory_items`, `model_runs`, `events`, `event_items`, `inventory_transactions`, `alerts`).
   - Transfer all existing records in dependency order (8 users, 10 items, 1 event, 1 event_item, 11 transactions).
   - Reset PostgreSQL primary key sequence generators (`setval`) to prevent future ID collision errors.
   - Verify that 31/31 records match between SQLite and PostgreSQL.

4. Run the PostgreSQL verification test:
   ```bash
   .\venv\Scripts\python.exe scripts\test_postgres_connection.py "PASTE_YOUR_EXTERNAL_DATABASE_URL_HERE"
   ```
   *Expected output: All 7 tables present, counts verified, and authentication checks passed.*

---

## Step 4: Create the Render Web Service

1. In your Render Dashboard, click **New +** and select **Web Service**.
2. Under **Connect a repository**, select your GitHub repository.
3. Configure the Web Service settings:
   - **Name**: `event-inventory-app`
   - **Region**: *Select the exact same region as your PostgreSQL database created in Step 1.*
   - **Branch**: `main`
   - **Root Directory**: `.` (leave empty or enter `.`)
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
     ```
   - **Plan**: `Free` (or `Starter`)

4. Scroll down and expand **Advanced**:
   - **Health Check Path**: `/api/health`
   - **Auto-Deploy**: `Yes` (deploys automatically when you push to `main`)

---

## Step 5: Configure Environment Variables in Render

In the Web Service creation screen (or under the **Environment** tab of your service), add the following environment variables:

| Key | Value | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | *Paste your **Internal Database URL*** | Starts with `postgres://...` (the app automatically converts it to `postgresql://` for SQLAlchemy 2.0). |
| `SECRET_KEY` | *Generate a 64-char hex key* | See command below. Do not use the default dev key. |
| `FLASK_ENV` | `production` | Enables production security policies and strict cookie protections. |
| `PYTHON_VERSION` | `3.11.9` | Matches the tested runtime environment. |
| `SESSION_COOKIE_SECURE` | `True` | Enforces HTTPS-only cookies on Render. |
| `SESSION_COOKIE_HTTPONLY` | `True` | Protects session tokens from client-side scripts. |
| `SESSION_COOKIE_SAMESITE` | `Lax` | Prevents CSRF while permitting top-level navigation. |

### How to Generate a Secure `SECRET_KEY`:
Run this one-liner in your local terminal:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Copy the generated 64-character string and paste it into the `SECRET_KEY` field in Render.

---

## Step 6: Trigger Deployment & Verify

1. Click **Create Web Service** (or **Deploy Latest Commit**).
2. Monitor the **Logs** tab:
   - Python dependencies will install (`Flask`, `SQLAlchemy`, `psycopg2-binary`, `gunicorn`, etc.).
   - Gunicorn will bind to `0.0.0.0:$PORT`.
   - Render will verify the health-check path `/api/health`.
   - You will see: `==> Your service is live at https://event-inventory-app.onrender.com`.

---

## Step 7: Post-Deployment Verification Checklist

Verify your live application using these steps:

1. **Health Check**:
   - Open: `https://your-app-name.onrender.com/api/health`
   - Expected response: `{"status": "healthy", "database": "connected"}` (HTTP 200).

2. **Existing User Authentication**:
   - Navigate to `https://your-app-name.onrender.com/login`.
   - Log in with existing migrated credentials:
     - **Admin**: `admin` / `Admin@123`
     - **Organizer**: `organizer` / `Organizer@123`
   - Confirm successful authentication and redirection to `/dashboard`.

3. **New User Registration**:
   - Open an Incognito window and visit `https://your-app-name.onrender.com/login#register`.
   - Register a new account (e.g. `test_render_user`, `render_test@example.com`, password: `Password123!`).
   - Confirm registration succeeds and redirects into the dashboard.

4. **Duplicate Prevention**:
   - Attempt to register again with the same username or email.
   - Confirm a clear error is displayed and duplicate records are rejected.

5. **Incorrect Password Rejection**:
   - Attempt login with `admin` and an incorrect password.
   - Confirm access is denied with `Invalid username or password.` (HTTP 401).

6. **Logout Verification**:
   - Click the user profile / Logout button.
   - Confirm session cookie is invalidated and you are returned to `/login`.

7. **Persistence Across Redeployments**:
   - In Render Dashboard, click **Manual Deploy** > **Deploy latest commit**.
   - After the redeploy completes, verify you can still log in with the new user registered in Step 3.
   - All user records and inventory data persist in the dedicated Render PostgreSQL instance.

---

## Security Reminders

- **Never** commit `.env` or database connection strings to GitHub.
- Keep `database/backups/event_inventory_backup.db` stored safely on your local machine as an offline backup.
- Render Free tier spins down web services after 15 minutes of inactivity; the first request after spin-down may take ~30–50 seconds to cold start.
