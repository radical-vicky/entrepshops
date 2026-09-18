#!/bin/bash
set -o errexit

echo "=== Starting build ==="

# Create the virtual environment
uv venv .venv

# Install dependencies using uv's native command
# The --python flag points uv to the venv's Python interpreter
uv pip install --python .venv/bin/python -r requirements.txt

# Run Django commands using the venv's Python
echo "=== Collecting static files ==="
.venv/bin/python manage.py collectstatic --noinput --clear

echo "=== Running migrations ==="
.venv/bin/python manage.py migrate --noinput

echo "=== Build complete ==="