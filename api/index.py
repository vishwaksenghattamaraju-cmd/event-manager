import os
import sys
import traceback
from pathlib import Path

# Add root directory to sys.path so backend package can be resolved
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

try:
    from wsgi import app

    _wsgi_app = app.wsgi_app

    def vercel_path_fix(environ, start_response):
        # 1. Primary: Check X-Target-Path header sent by frontend API client
        target = environ.get("HTTP_X_TARGET_PATH")
        if target:
            environ["PATH_INFO"] = target.split("?")[0]
            if "?" in target:
                environ["QUERY_STRING"] = target.split("?", 1)[1]
        # 2. Query string fallback: __path__ or target_path
        elif "__path__=" in environ.get("QUERY_STRING", "") or "target_path=" in environ.get("QUERY_STRING", ""):
            import urllib.parse
            params = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))
            param_key = "__path__" if "__path__" in params else "target_path"
            if param_key in params and params[param_key]:
                environ["PATH_INFO"] = params[param_key][0]
                remaining = [(k, v) for k, vs in params.items() if k != param_key for v in vs]
                environ["QUERY_STRING"] = urllib.parse.urlencode(remaining)
        # 3. Standard proxy headers fallback
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

        return _wsgi_app(environ, start_response)

    app.wsgi_app = vercel_path_fix
except Exception as e:
    err_tb = traceback.format_exc()
    print("FATAL STARTUP ERROR in wsgi:", err_tb)
    from flask import Flask
    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def catch_all(path):
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Server Startup Diagnostic</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 2rem; background: #0f172a; color: #f8fafc; line-height: 1.5; }}
                .card {{ background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 12px; padding: 1.5rem; max-width: 800px; margin: 0 auto; }}
                h2 {{ color: #f87171; margin-top: 0; }}
                pre {{ background: #020617; border: 1px solid rgba(255,255,255,0.1); padding: 1rem; border-radius: 8px; color: #fca5a5; overflow-x: auto; font-size: 0.85rem; font-family: monospace; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>⚠️ Server Initialization Diagnostic</h2>
                <p>The application encountered an exception during cold start:</p>
                <pre>{err_tb}</pre>
            </div>
        </body>
        </html>
        """, 500
