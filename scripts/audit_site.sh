#!/bin/bash

echo "=============================="
echo "FULL PROFESSIONAL SITE AUDIT"
echo "=============================="

echo ""
echo "1. Activating environment..."
source env/bin/activate || exit 1


echo ""
echo "2. Django deployment checks..."
python manage.py check --deploy || exit 1


echo ""
echo "3. Migration safety check..."
python manage.py makemigrations --check --dry-run || exit 1


echo ""
echo "4. Backend tests..."
pytest || exit 1


echo ""
echo "5. Lint checks..."
flake8 . || exit 1


echo ""
echo "6. Security scan..."
bandit -r . -x ./env,./node_modules,./staticfiles,./media,./playwright-report || exit 1


echo ""
echo "7. Dependency vulnerability scan..."
safety check || true


echo ""
echo "8. Static files integrity..."
python manage.py collectstatic --noinput --dry-run || exit 1


echo ""
echo "9. Detect unused static files..."
python manage.py findstatic css --verbosity 0 > /tmp/static_used.txt
find static -type f > /tmp/static_all.txt
comm -23 /tmp/static_all.txt /tmp/static_used.txt || true


echo ""
echo "10. Detect unused templates..."
grep -R "{% include" templates > /tmp/template_links.txt
find templates -type f > /tmp/template_all.txt
comm -23 /tmp/template_all.txt /tmp/template_links.txt || true


echo ""
echo "11. Discover broken URLs..."
python manage.py show_urls | awk '{print $2}' | while read url; do
  curl -s -o /dev/null -w "%{http_code} $url\n" http://127.0.0.1:8000$url
done


echo ""
echo "12. Run UI tests..."
npx playwright test || exit 1


echo ""
echo "13. Run Lighthouse performance audit..."
npx lighthouse http://127.0.0.1:8000 --quiet --chrome-flags="--headless"


echo ""
echo "14. API load test..."
npx autocannon http://127.0.0.1:8000


echo ""
echo "15. Container compatibility test..."
docker compose build || exit 1


echo ""
echo "16. Check unused Python imports..."
pip install vulture >/dev/null 2>&1
vulture .


echo ""
echo "17. Bundle size analysis..."
du -sh static/
du -sh media/

echo ""
echo "Removing unused static files..."
comm -23 /tmp/static_all.txt /tmp/static_used.txt | xargs rm -f

echo ""
echo "18. Gunicorn stress test (simulated traffic)..."
npx autocannon -c 50 -d 20 http://127.0.0.1:8000


echo ""
echo "19. Detect largest static files..."
find static -type f -exec du -h {} + | sort -rh | head -20


echo ""
echo "20. Detect largest media files..."
find media -type f -exec du -h {} + | sort -rh | head -20


echo ""
echo "21. Detect unused Django URLs..."
python manage.py show_urls | awk '{print $2}' > all_urls.txt
grep -R "href=" templates/ | cut -d'"' -f2 | grep '^/' > used_urls.txt
comm -23 all_urls.txt used_urls.txt || true


echo ""
echo "22. Endpoint response-time benchmark..."
for url in $(python manage.py show_urls | awk '{print $2}'); do
  curl -o /dev/null -s -w "%{time_total}s %{url_effective}\n" http://127.0.0.1:8000$url
done

echo ""
echo "=============================="
echo "AUDIT COMPLETE"
echo "=============================="
