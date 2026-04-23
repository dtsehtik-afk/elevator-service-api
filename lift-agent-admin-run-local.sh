#!/bin/bash
# Run lift-agent-admin locally (no Docker needed, uses SQLite)
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# Backend
echo "=== Starting backend on :8001 ==="
cd "$ROOT/lift-agent-admin-backend"

if [ ! -d ".venv" ]; then
  # Ensure python3-venv is available
  if ! python3 -m venv --help &>/dev/null; then
    echo "Installing python3-venv..."
    sudo apt-get install -y python3-venv python3-pip
  fi
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip -q
  .venv/bin/pip install -r requirements.txt
fi

.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

sleep 2

# Seed first admin user (ignore error if already exists)
curl -s -X POST http://localhost:8001/auth/seed-admin | python3 -m json.tool || true

# Frontend
echo ""
echo "=== Starting frontend on :5174 ==="
cd "$ROOT/lift-agent-admin-frontend"
if [ ! -d "node_modules" ]; then
  npm install
fi
npm run dev &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

echo ""
echo "================================================"
echo " Admin panel: http://localhost:5174"
echo " API docs:    http://localhost:8001/docs"
echo " Login:       admin@lift-agent.com / changeme123"
echo "================================================"
echo ""
echo "Press Ctrl+C to stop"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
