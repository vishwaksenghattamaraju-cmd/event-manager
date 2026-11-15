# Vercel database setup (required)

This application uses SQLite for local development. SQLite files stored in a Vercel
function's filesystem (including `/tmp`) are temporary and are not shared reliably
between serverless instances. Do not use SQLite for production accounts.

## 1. Create a persistent PostgreSQL database

Create a PostgreSQL database with Neon or Supabase. Copy its connection string.
Use the provider's pooled connection string if it recommends one for serverless
applications. The connection string must use `postgresql://` (or a supported
SQLAlchemy PostgreSQL driver URL).

## 2. Configure Vercel

In Vercel, open **Project → Settings → Environment Variables** and add:

- `DATABASE_URL`: the PostgreSQL connection string
- `SECRET_KEY`: a newly generated, long random secret (do not reuse the example key)

Set both for **Production** (and Preview too, if you use Preview deployments).
Do not add the database URL or secret to source control.

Generate a secret locally with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 3. Redeploy and verify

Redeploy after saving the variables. The app creates missing tables at startup.
Then open:

`https://YOUR-DOMAIN/api/health`

A working database should return HTTP 200 and:

```json
{"status":"healthy","database":"connected"}
```

A database connection failure returns HTTP 503 and a generic error. Check the
Vercel Function Logs for the detailed server-side exception; never paste database
credentials into support messages.

## 4. Test account persistence

1. Register a new test account.
2. Log out.
3. Log in again with the same username/email and password.
4. Refresh the dashboard and verify the session.
5. Repeat after a new deployment.

The user record is stored in PostgreSQL; logout only clears the browser session.

## Important migration note

Accounts previously created in a temporary SQLite database are not automatically
copied to PostgreSQL. If you need to retain them, export and migrate the user records
securely before switching production traffic. Otherwise, register accounts again
after the persistent database is connected.

## Security notes

- The frontend no longer stores account passwords in `localStorage`.
- The old browser-side "re-register on 401" workaround has been removed.
- Production startup fails if PostgreSQL is missing or cannot initialize.
- `/api/health` executes a real `SELECT 1` database check.
- Demo admin/organizer accounts are not seeded on Vercel by default.
