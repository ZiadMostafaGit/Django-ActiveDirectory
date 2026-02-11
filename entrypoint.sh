#!/usr/bin/env bash
set -e

echo "Starting Django application..."

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear 2>&1 | tail -5

# Run migrations with retries
echo "Running database migrations..."
for i in {1..30}; do
  if python manage.py migrate --noinput 2>&1; then
    echo "Migrations completed successfully!"
    break
  fi
  if [ $i -lt 30 ]; then
    echo "Attempt $i/30: Waiting for database..."
    sleep 2
  else
    echo "Failed to run migrations after 30 attempts"
    exit 1
  fi
done

# Run AD user sync on startup
echo "Synchronizing users from Active Directory..."
python manage.py sync_ad_users --update || echo "AD Sync failed (moving on...)"

echo "Starting Gunicorn server on 0.0.0.0:8000"
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
