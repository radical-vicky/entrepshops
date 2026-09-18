#!/bin/bash
# Runs during every Vercel build (see vercel.json's static-build step).
set -o errexit

echo "=== Starting build ==="
echo "Python version:"
python3 --version

echo "uv version:"
uv --version

# Create virtual environment
echo "=== Creating virtual environment ==="
uv venv .venv

# Activate virtual environment
echo "=== Activating virtual environment ==="
source .venv/bin/activate

# Verify activation
echo "Python in venv: $(which python)"

# Install dependencies
echo "=== Installing dependencies ==="
uv pip install -r requirements.txt

# Verify Django
echo "=== Verifying Django ==="
python -c "import django; print('Django:', django.get_version())"

# Collect static files
echo "=== Collecting static files ==="
python manage.py collectstatic --noinput --clear

# Run migrations
echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Build complete ==="