#!/bin/bash
# ==============================================================================
# Production Rollback Script (called via SSH from GitHub Actions)
# ==============================================================================
# Usage: rollback.sh <image_tag>
#   image_tag: REQUIRED — the SHA tag to roll back to (e.g., sha-abc123def456)
# ==============================================================================
set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "❌ Usage: $0 <image_tag>"
    echo "   Example: $0 sha-abc123def456"
    exit 1
fi

TAG="$1"
FULL_IMAGE="ghcr.io/yuvraj-pb23/ohs:${TAG}"

echo "========================================="
echo "🔄 ROLLBACK to: ${FULL_IMAGE}"
echo "   Time: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "========================================="

cd /app/OHS

echo "[1/4] Pulling rollback image..."
docker pull "${FULL_IMAGE}"

echo "[2/4] Stopping current web service..."
docker compose --profile prod stop web worker scheduler

echo "[3/4] Starting services with rollback image..."
docker compose --profile prod up -d --remove-orphans

echo "[4/4] Verifying post-rollback health..."
sleep 15
docker compose --profile prod ps

# Quick health check
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://localhost/ 2>/dev/null || echo "000")
echo "Health check: HTTP ${HTTP_CODE}"

echo "========================================="
echo "✅ Rollback to ${TAG} completed"
echo "   Time: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "========================================="
