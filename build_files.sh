#!/bin/bash
set -o errexit

echo "=== Starting build ==="

# Create the virtual environment
uv venv .venv

# Install dependencies INTO the venv using the explicit Python path
# AND the --break-system-packages flag to bypass PEP 668 protection
uv pip install --python .venv/bin/python --break-system-packages -r requirements.txt

# Run Django commands using the venv's Python interpreter directly
echo "=== Collecting static files ==="
.venv/bin/python manage.py collectstatic --noinput --clear

echo "=== Running migrations ==="
.venv/bin/python manage.py migrate --noinput

echo "=== Build complete ==="