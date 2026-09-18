#!/bin/bash
set -o errexit

echo "=== Starting build ==="

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput --clear

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Build complete ==="
