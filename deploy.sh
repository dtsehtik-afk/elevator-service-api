#!/usr/bin/env bash
# deploy.sh — push latest main to GCP + Hetzner in the background
# Usage: ./deploy.sh [gcp|hetzner|all]
set -euo pipefail

GCP="35.226.208.142"
HETZNER="5.78.129.4"
APP_DIR="/opt/elevator-service-api"
LOG_DIR="/tmp"

TARGET="${1:-all}"

_deploy() {
  local name="$1"
  local host="$2"
  local log="$LOG_DIR/deploy_${name}.log"

  echo "🚀 Deploying to $name ($host) — log: $log"

  ssh -o StrictHostKeyChecking=no "root@$host" bash -s << 'REMOTE' > "$log" 2>&1 &
    set -euo pipefail
    cd /opt/elevator-service-api
    git pull origin main
    docker compose build --no-cache app
    docker compose up -d --no-deps app
    docker compose exec -T app alembic upgrade head 2>/dev/null || true
    echo "✅ Done at $(date)"
REMOTE

  local pid=$!
  echo "   PID $pid — tail -f $log"
}

case "$TARGET" in
  gcp)     _deploy gcp     "$GCP"     ;;
  hetzner) _deploy hetzner "$HETZNER" ;;
  all)
    _deploy gcp     "$GCP"
    _deploy hetzner "$HETZNER"
    ;;
  *)
    echo "Usage: $0 [gcp|hetzner|all]"
    exit 1
    ;;
esac

echo ""
echo "Both deploys running in background."
echo "Watch logs:"
echo "  tail -f $LOG_DIR/deploy_gcp.log"
echo "  tail -f $LOG_DIR/deploy_hetzner.log"
