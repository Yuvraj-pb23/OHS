#!/bin/bash
# ==============================================================================
# Production Deployment Script (called via SSH from GitHub Actions)
# ==============================================================================
# Usage: deploy.sh [image_tag]
#   image_tag: optional — full image reference (e.g., ghcr.io/yuvraj-pb23/ohs:sha-abc123)
#              If not provided, pulls :latest
# ==============================================================================
set -euo pipefail

echo "========================================="
echo "Executing Production Deployment..."
echo "========================================="

cd /app/OHS

IMAGE_TAG="${1:-ghcr.io/yuvraj-pb23/ohs:latest}"
echo "Image: ${IMAGE_TAG}"
echo "Time:  $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

echo "[1/5] Pulling latest code..."
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Current branch: $CURRENT_BRANCH"
git fetch origin "$CURRENT_BRANCH" --quiet
git reset --hard "origin/$CURRENT_BRANCH"

echo "[2/5] Pulling container images..."
docker compose --profile prod pull

echo "[3/5] Recreating services..."
docker compose --profile prod up -d --remove-orphans

echo "[4/5] Cleaning up dangling images..."
docker image prune -f

echo "[5/5] Verifying deployment health..."
sleep 15
docker compose --profile prod ps

echo "========================================="
echo "Deployment Finished Successfully!"
echo "  Image: ${IMAGE_TAG}"
echo "  Time:  $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "========================================="
