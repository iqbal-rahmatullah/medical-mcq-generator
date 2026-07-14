#!/usr/bin/env bash
# Run backend (FastAPI/uvicorn) + frontend (Next.js) together.
# Usage: ./dev.sh   (Ctrl-C stops both)
set -euo pipefail
cd "$(dirname "$0")"

BACKEND_PORT="${BACKEND_PORT:-8000}"

trap 'kill 0' EXIT   # Ctrl-C / exit kills the whole process group (both servers)

# --reload-dir app: only watch the app package. Without it WatchFiles crawls the
# whole root (.venv, .cache 2.3GB, data/, HF caches) on startup — slow/hangs on
# first launch.
.venv/bin/python -m uvicorn app.main:app --reload --reload-dir app --port "$BACKEND_PORT" &
(cd web && npm run dev) &
wait
