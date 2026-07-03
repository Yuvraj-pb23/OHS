#!/bin/bash
set -e
BACKUP_DIR="/app/backups"
mkdir -p "$BACKUP_DIR"
echo "Running Database Backup..."
if docker ps | grep -q ohs_db; then
    docker exec -t ohs_db pg_dumpall -c -U ohs_user > "$BACKUP_DIR/db_backup_$(date +%F).sql"
else
    cp /app/data/db.sqlite3 "$BACKUP_DIR/db_backup_$(date +%F).sqlite3"
fi
echo "Backup saved in $BACKUP_DIR"
