#!/bin/bash

mkdir -p logs

echo "Starting Django server with logging..."

python manage.py runserver 2>&1 | tee logs/server_$(date +%F_%H-%M).log
