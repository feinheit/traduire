import os

import speckenv
from django.core.asgi import get_asgi_application


speckenv.read_speckenv()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")
application = get_asgi_application()
