#!/bin/bash

echo "Running backend tests..."
pytest || exit 1

echo "Checking migrations..."
python manage.py makemigrations --check --dry-run || exit 1

echo "Running Django deploy checks..."
python manage.py check --deploy || exit 1

echo "Running lint checks..."
flake8 . || exit 1

echo "Running security scan..."
bandit -r . || exit 1

echo "All backend checks passed."
