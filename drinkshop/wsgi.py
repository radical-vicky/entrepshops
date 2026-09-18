import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drinkshop.settings')

application = get_wsgi_application()

# Vercel's Python runtime (@vercel/python) looks for a variable named `app`
# as the WSGI entrypoint. `application` above is the Django/WSGI standard
# name used by manage.py and gunicorn — keep both so nothing else breaks.
app = application
