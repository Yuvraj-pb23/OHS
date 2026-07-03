#!/bin/bash
set -e
echo "========================================="
echo "Executing Deployment Tasks..."
echo "========================================="

cd /app/OHS

echo "[1/5] Pulling latest code..."
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Current branch: $CURRENT_BRANCH"
git pull origin "$CURRENT_BRANCH"

echo "[2/5] Pulling latest container images..."
docker compose --profile prod pull

echo "[3/5] Rebuilding and restarting services (zero-downtime)..."
docker compose --profile prod up -d --remove-orphans

echo "[4/5] Cleaning up old images..."
docker image prune -f

echo "[5/5] Verifying deployment health..."
sleep 10
docker compose --profile prod ps

echo "========================================="
echo "Deployment Finished Successfully!"
echo "========================================="
