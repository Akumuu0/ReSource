#!/bin/bash
# Puts ReSource online on PythonAnywhere (README section 6).
# Run it in a PythonAnywhere Bash console, from the project folder:
#     bash deploy/pythonanywhere.sh
# Running it again resets the demo data.
set -e                      # stop at the first error
cd "$(dirname "$0")/.."     # go to the project folder
PROJECT_DIR="$(pwd)"

# The web app must exist first: PythonAnywhere creates its WSGI file in /var/www.
WSGI_FILE=$(ls /var/www/*_wsgi.py 2>/dev/null | head -n 1)
if [ -z "$WSGI_FILE" ]; then
    echo "No web app yet. Create it on the Web tab (Manual configuration, Python 3.12), then run this again."
    exit 1
fi

echo "1/4 Virtual environment and packages"
python3.12 -m venv .venv
.venv/bin/pip install --quiet -r requirements.txt

echo "2/4 Random secret key, kept out of the code"
if [ ! -f secret_key.txt ]; then
    .venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))" > secret_key.txt
fi

echo "3/4 Database, CSS files and demo data"
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py seed

echo "4/4 WSGI file"
sed -e "s|USERNAME|$(whoami)|g" -e "s|PROJECT_DIR|$PROJECT_DIR|g" deploy/pythonanywhere_wsgi.py > "$WSGI_FILE"

echo
echo "Done. On the Web tab set:"
echo "  Virtualenv:            $PROJECT_DIR/.venv"
echo "  Static files: URL /static/  Directory $PROJECT_DIR/staticfiles"
echo "then press the green Reload button."
