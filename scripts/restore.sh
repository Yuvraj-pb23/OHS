#!/bin/bash
set -e
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file_path>"
    exit 1
fi
FILE=$1
echo "Restoring Database from: $FILE..."
if [[ "$FILE" == *.sql ]]; then
    cat "$FILE" | docker exec -i ohs_db psql -U ohs_user -d ohs_db
else
    cp "$FILE" /app/data/db.sqlite3
fi
echo "Restore operation completed."
