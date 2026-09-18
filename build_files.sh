#!/bin/bash
set -o errexit

echo "=== Starting build ==="

python manage.py collectstatic --noinput --clear
python manage.py migrate --noinput

echo "=== Build complete ==="
