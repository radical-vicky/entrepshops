"""
WSGI config for drinkshop project.

This runs collectstatic automatically at startup — Vercel's build system
doesn't run build_files.sh, so we do it here where we KNOW it will execute.
"""
import os
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drinkshop.settings')

# --- Run collectstatic at startup (idempotent, fast if already done) ---
try:
    import django
    django.setup()

    from django.conf import settings
    from django.core.management import call_command

    static_root = Path(settings.STATIC_ROOT)
    # Only collect if the staticfiles folder is missing or empty
    if not static_root.exists() or not any(static_root.iterdir()):
        print("=== collectstatic starting (staticfiles missing) ===")
        call_command('collectstatic', interactive=False, verbosity=0, clear=True)
        print("=== collectstatic done ===")
except Exception as e:
    print(f"collectstatic skipped: {e}")

# --- Normal WSGI setup ---
from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
