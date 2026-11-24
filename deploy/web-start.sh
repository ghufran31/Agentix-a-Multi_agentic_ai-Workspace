#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py setup_supervisor_checkpoints
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" --threads "${GUNICORN_THREADS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" --access-logfile - --error-logfile - \
    --access-logformat '%(h)s %(m)s %(U)s %(s)s %(L)s'
