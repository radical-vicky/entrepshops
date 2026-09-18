#!/bin/bash
# Runs during every Vercel build (see vercel.json's static-build step).
set -o errexit

<<<<<<< HEAD
echo "=== Starting build ==="
echo "Python version:"
python3 --version
=======
# static-build step doesn't provision a venv for us, and the
# interpreter uv points at is "externally managed" — so make our own.
uv venv .venv
source .venv/bin/activate

uv pip install -r requirements.txt
>>>>>>> 34ee5571bd460b82af6ea1c6d222e47cd3be8a47

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
echo "Pip in venv: $(which pip)"

# Install dependencies
echo "=== Installing dependencies ==="
uv pip install -r requirements.txt

# Verify Django is installed
echo "=== Verifying Django installation ==="
python -c "import django; print('Django version:', django.get_version())"

# Collect static files
echo "=== Collecting static files ==="
python manage.py collectstatic --noinput --clear

# Run migrations
echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Build complete ==="