#!/bin/bash

echo "=============================="
echo "FULL PROJECT VALIDATION START"
echo "=============================="

echo ""
echo "1. Django system check..."
python manage.py check

echo ""
echo "2. Deployment readiness check..."
python manage.py check --deploy

echo ""
echo "3. Database migration safety..."
python manage.py makemigrations --check --dry-run

echo ""
echo "4. Django tests..."
python manage.py test

echo ""
echo "5. Pytest backend tests..."
pytest

echo ""
echo "6. Lint check (flake8)..."
flake8

echo ""
echo "7. Security scan (Bandit)..."
bandit -r .

echo ""
echo "8. Dependency vulnerability scan..."
safety check || true

echo ""
echo "9. Playwright UI tests..."
npx playwright test || true

echo ""
echo "10. Existing audit script..."
bash scripts/audit_site.sh

echo ""
echo "=============================="
echo "ALL CHECKS COMPLETED ✅"
echo "=============================="
