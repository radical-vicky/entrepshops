#!/bin/bash
set -o errexit

echo "=== Starting build ==="

# Create virtual environment
uv venv .venv

# Install dependencies into the venv using uv's native command
# The --python flag forces uv to use the venv's Python, not system Python
uv pip install --python .venv/bin/python -r requirements.txt

# Run Django commands using venv's Python directly (no activation needed)
echo "=== Collecting static files ==="
.venv/bin/python manage.py collectstatic --noinput --clear

echo "=== Running migrations ==="
.venv/bin/python manage.py migrate --noinput

echo "=== Build complete ==="