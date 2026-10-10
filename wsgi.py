"""
WSGI Entrypoint for Production Deployment.
Used by Waitress (Windows/Cross-platform) or Gunicorn (Linux/Containers).
"""

import os
import sys
from pathlib import Path

# Ensure root workspace is in sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.app import create_app
from backend.config import Config

app = create_app(Config)

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Starting Event Inventory Production Server on http://0.0.0.0:{port}")
    serve(app, host="0.0.0.0", port=port, threads=8)
