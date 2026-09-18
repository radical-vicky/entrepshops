#!/bin/bash
set -o errexit

echo "=== Starting build ==="

# Create virtual environment (this should work as before)
uv venv .venv

# Install dependencies directly into the venv without activating it.
# This bypasses any PATH or activation issues.
uv pip install --python .venv/bin/python -r requirements.txt

# Run Django commands using the venv's Python interpreter explicitly.
echo "=== Collecting static files ==="
.venv/bin/python manage.py collectstatic --noinput --clear

echo "=== Running migrations ==="
.venv/bin/python manage.py migrate --noinput

echo "=== Build complete ==="