#!/bin/bash
set -eo pipefail

# Native hot-reload dev. The backend binds :4002 (NOT :8400 — that's taken by the
# deployed prod container) and the frontend is pointed at it so dev never talks to
# prod. Override with BACKEND_PORT if 4002 is busy.
BACKEND_PORT="${BACKEND_PORT:-4002}"

function run_frontend() {
  cd frontend && VITE_API_BASE_URL="http://localhost:${BACKEND_PORT}" pnpm run dev
}

function run_backend() {
  cd backend && ENVIRONMENT=DEVELOPMENT uv run gunicorn \
      -k bracket.uvicorn.RestartableUvicornWorker \
      bracket.app:app \
      --bind "localhost:${BACKEND_PORT}" \
      --workers 1 \
      --reload
}

(trap 'kill 0' SIGINT;
  run_frontend &
  run_backend
)
