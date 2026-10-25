#!/usr/bin/env bash
# One-command setup + run for Linux/macOS:  bash start_app.sh
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
echo "Starting app at http://127.0.0.1:5000  (Ctrl+C to stop)"
python backend/app.py
