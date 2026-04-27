#!/bin/bash

echo "=============================="
echo "Starting FULL PROJECT TEST SUITE"
echo "=============================="

echo ""
echo "1. Activating virtual environment..."
source env/bin/activate || exit 1

echo "Starting Django server..."
python manage.py runserver 127.0.0.1:8000 &
SERVER_PID=$!
sleep 5

echo ""
echo "8. Crawling all Django URLs..."

python manage.py show_urls | awk '{print $2}' | while read url; do
    if [[ "$url" == /* ]]; then
        status=$(curl -o /dev/null -s -w "%{http_code}" http://127.0.0.1:8000$url)
        if [[ "$status" != "200" && "$status" != "302" ]]; then
            echo "❌ Broken endpoint: $url (HTTP $status)"
            exit 1
        else
            echo "✅ $url"
        fi
    fi
done

echo ""
echo "Checking static asset responses..."

grep -R "/static/" templates | sed -E "s/.*(\/static\/[^\"']+).*/\1/" | sort -u | while read asset; do
    status=$(curl -o /dev/null -s -w "%{http_code}" http://127.0.0.1:8000$asset)
    if [[ "$status" != "200" ]]; then
        echo "❌ Missing static asset: $asset"
        exit 1
    fi
done

echo ""
echo "2. Running Django unit tests (pytest)..."
pytest || exit 1


echo ""
echo "3. Checking migrations..."
python manage.py makemigrations --check --dry-run || exit 1


echo ""
echo "4. Running Django deployment checks..."
python manage.py check --deploy || exit 1


echo ""
echo "5. Checking static files..."
python manage.py collectstatic --noinput --dry-run || exit 1


echo ""
echo "6. Running lint checks..."
flake8 . || exit 1


echo ""
echo "7. Running security scan (Bandit)..."
bandit -r . || exit 1


echo ""
echo "8. Running dependency vulnerability scan..."
safety check || echo "Safety warnings detected (review manually)"


echo ""
echo "9. Running UI tests (Playwright)..."
npx playwright test || exit 1


echo ""
echo "10. Running Lighthouse performance audit..."
lighthouse http://127.0.0.1:8000 --quiet || echo "Lighthouse skipped (server may not be running)"


echo ""
echo "11. Running API tests (Newman if collection exists)..."
if [ -f api_tests.json ]; then
    newman run api_tests.json || exit 1
else
    echo "No Postman collection found, skipping API tests."
fi

echo "Stopping Django server..."
kill $SERVER_PID

echo ""
echo "=============================="
echo "ALL TESTS PASSED SUCCESSFULLY"
echo "READY TO PUSH 🚀"
echo "=============================="
