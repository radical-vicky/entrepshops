#!/bin/bash
# Runs during every Vercel build (see vercel.json's static-build step).
set -o errexit

# static-build step doesn't provision a venv for us, and the
# interpreter uv points at is "externally managed" — so make our own.
uv venv .venv
source .venv/bin/activate

uv pip install -r requirements.txt

python manage.py collectstatic --noinput --clear

python manage.py migrate --noinput
