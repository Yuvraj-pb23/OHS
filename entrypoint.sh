#!/bin/bash
# ==============================================================================
# Production Entrypoint Script
# ==============================================================================
# Supports three container roles via CONTAINER_ROLE environment variable:
#   - web       : Runs migrations, collectstatic, then Gunicorn
#   - worker    : Runs Celery worker (NO migrations, NO collectstatic)
#   - beat      : Runs Celery beat scheduler (NO migrations, NO collectstatic)
#
# If CONTAINER_ROLE is not set, falls back to whatever CMD is passed.
# ==============================================================================
set -e

echo "=== OHS Entrypoint | Role: ${CONTAINER_ROLE:-default} ==="

# --------------------------------------------------------------------------
# Common: Set default database path for SQLite fallback
# --------------------------------------------------------------------------
if [ -z "$DATABASE_URL" ] && [ -z "$DATABASE_PATH" ]; then
    export DATABASE_PATH="/app/data/db.sqlite3"
    echo "Setting SQLite database path to: $DATABASE_PATH"
fi

# --------------------------------------------------------------------------
# Role-based startup logic
# --------------------------------------------------------------------------
case "${CONTAINER_ROLE}" in
    web)
        echo "[web] Applying database migrations..."
        python manage.py migrate --noinput

        echo "[web] Collecting static files..."
        python manage.py collectstatic --noinput

        echo "[web] Starting Gunicorn..."
        exec gunicorn OHS.wsgi:application \
            --bind 0.0.0.0:8000 \
            --workers "${GUNICORN_WORKERS:-3}" \
            --threads "${GUNICORN_THREADS:-2}" \
            --worker-tmp-dir /dev/shm \
            --worker-class gthread \
            --no-control-socket \
            --timeout 120 \
            --graceful-timeout 30 \
            --keep-alive 5 \
            --max-requests 1000 \
            --max-requests-jitter 50 \
            --access-logfile - \
            --error-logfile - \
            --log-level info
        ;;

    worker)
        echo "[worker] Starting Celery worker..."
        exec celery -A OHS worker \
            --loglevel=info \
            --concurrency="${CELERY_CONCURRENCY:-2}" \
            --max-tasks-per-child=100 \
            --without-heartbeat \
            --without-gossip \
            --without-mingle
        ;;

    beat)
        echo "[beat] Starting Celery beat scheduler..."
        exec celery -A OHS beat \
            --loglevel=info \
            --schedule=/tmp/celerybeat-schedule \
            --pidfile=/tmp/celerybeat.pid
        ;;

    *)
        # Fallback: run whatever CMD was passed (backward compatible)
        echo "[default] Starting with command: $@"
        exec "$@"
        ;;
esac
