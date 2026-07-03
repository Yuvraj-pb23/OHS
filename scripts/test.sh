#!/bin/bash
set -e

echo "=== Running Unit Tests ==="
python manage.py test

echo "=== Running Code Quality Checks ==="
flake8 .

echo "=== Running Security Checks ==="
bandit -r .

echo "=== Testing Database Connection ==="
python manage.py dbshell <<EOF
SELECT 1;
EOF

echo "All tests completed successfully!"
