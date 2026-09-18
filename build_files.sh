#!/bin/bash
# Runs during every Vercel build (see vercel.json's static-build step).
# This is where "automatic migration on deploy" actually happens — Vercel
# has no Heroku-style release phase, so build time is the right place to
# run it. Requires DATABASE_URL to be set in the Vercel project's env vars
# and reachable from the build environment (Vercel Postgres, Neon,
# Supabase, etc. all work — see README "Deploying to Vercel").
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput --clear

python manage.py migrate --noinput
