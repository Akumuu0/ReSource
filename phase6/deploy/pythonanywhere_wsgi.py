"""WSGI file for PythonAnywhere (README section 6).

deploy/pythonanywhere.sh copies this file over the web app's WSGI file and
fills in USERNAME and PROJECT_DIR. PythonAnywhere runs it to start the site.
"""
import os
import sys
from pathlib import Path

PROJECT = Path("PROJECT_DIR")
sys.path.insert(0, str(PROJECT))

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["DJANGO_DEBUG"] = "0"
# The site's address (US and EU PythonAnywhere servers).
os.environ["DJANGO_ALLOWED_HOSTS"] = "USERNAME.pythonanywhere.com,USERNAME.eu.pythonanywhere.com"
# The secret key was made by deploy/pythonanywhere.sh; it is not in the code.
os.environ["DJANGO_SECRET_KEY"] = (PROJECT / "secret_key.txt").read_text().strip()

# Optional: put a Gemini API key in ai_key.txt to use the real AI instead of the fallbacks.
key_file = PROJECT / "ai_key.txt"
if key_file.exists():
    os.environ["GEMINI_API_KEY"] = key_file.read_text().strip()

from django.core.wsgi import get_wsgi_application  # noqa: E402 (needs the settings above)

application = get_wsgi_application()
