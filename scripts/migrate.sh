#!/bin/bash
set -e
echo "Executing Database Migrations..."
docker-compose --profile prod exec -T web python manage.py migrate --noinput
