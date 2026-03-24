#!/usr/bin/env bash
set -euo pipefail

# Start Redis, frontend (Node), and backend (Uvicorn) in one container.
# Exit the container if any process exits unexpectedly.
redis-server --save "" --appendonly no --bind 127.0.0.1 --port 6379 &
REDIS_PID=$!

node /app/frontend/server.js &
FRONTEND_PID=$!

uvicorn app.main:app --host 0.0.0.0 --port 17321 &
BACKEND_PID=$!

cleanup() {
  kill "${REDIS_PID}" "${FRONTEND_PID}" "${BACKEND_PID}" 2>/dev/null || true
}

trap cleanup TERM INT EXIT

# wait -n returns the exit code of the first process that finishes
wait -n "${REDIS_PID}" "${FRONTEND_PID}" "${BACKEND_PID}"
EXIT_CODE=$?
exit ${EXIT_CODE}
